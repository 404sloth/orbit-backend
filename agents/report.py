"""
Report Agent - Generates Excel reports and manages session-based data caching.
"""
import os
import uuid
import time
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from core.session import session_data, REPORTS_TEMP_DIR, init_reports_dir
from tools.sql import execute_read_query
from db.schema import get_bcnf_schema, get_table_names

# Ensure temp directory exists
init_reports_dir()

def report_node(state: GraphState, config: Dict[str, Any]) -> dict:
    """
    Report Agent node.
    1. Analyzes user request to determine the required SQL query.
    2. Executes the query and fetches data.
    3. Generates an Excel file.
    4. Caches data for future image generation.
    5. Returns a download link.
    """
    session_id = config.get("configurable", {}).get("thread_id", "default_session")
    user_query = state["messages"][-1].content
    
    logger.info("Report Agent processing request", session_id=session_id, query=user_query)

    llm = get_llm(temperature=0)
    
    # --- Step 1: Generate SQL query ---
    table_names = get_table_names()
    schema = get_bcnf_schema(table_names)
    
    sql_gen_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a SQL expert for an executive dashboard. Based on the user's request and the database schema, generate a single SELECT SQL query to fetch the data needed for a report.
        
SCHEMA:
{schema}

RELATIONSHIP HINTS:
- To link PROJECTS and VENDORS, you MUST use the `statements_of_work` table: 
  `projects p JOIN statements_of_work sow ON p.project_id = sow.project_id JOIN vendors v ON sow.vendor_id = v.vendor_id`
- To get MILESTONES for a project: 
  `projects p JOIN statements_of_work sow ON p.project_id = sow.project_id JOIN milestones m ON sow.sow_id = m.sow_id`
- CLIENTS are linked to PROJECTS via `client_id`.

RULES:
- Return ONLY the SQL query string. 
- No markdown formatting, no backticks, no preamble.
- Only SELECT statements are allowed.
- Use explicit column names (e.g., p.project_name, v.vendor_name).
- If the request is for "all projects" and "all vendors", ensure you JOIN them correctly via SOW.
"""),
        ("human", "{user_query}")
    ])
    
    chain = sql_gen_prompt | llm
    sql_query = chain.invoke({"schema": schema, "user_query": user_query}).content.strip()
    
    # Remove markdown code blocks if any
    if sql_query.startswith("```"):
        sql_query = sql_query.split("\n")[1:-1]
        sql_query = "\n".join(sql_query).strip()
    
    logger.info("Generated SQL for report", sql=sql_query)
    
    # --- Step 2: Execute SQL ---
    try:
        import json
        sql_result_json = execute_read_query.invoke({"query": sql_query})
        sql_result = json.loads(sql_result_json)
        
        if sql_result["status"] != "success":
            return {"messages": [AIMessage(content=f"Failed to fetch data for report: {sql_result['message']}")]}
        
        data = sql_result["data"]
        if not data:
            return {"messages": [AIMessage(content="The query returned no data. I cannot generate a report.")]}
            
    except Exception as e:
        logger.error("Error executing SQL for report", error=str(e))
        return {"messages": [AIMessage(content=f"Error fetching data: {str(e)}")]}

    # --- Step 3: Generate Excel ---
    try:
        df = pd.DataFrame(data)
        
        # Clean column names for Excel
        df.columns = [str(col).replace("_", " ").title() for col in df.columns]
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{session_id[:8]}_{timestamp}.xlsx"
        filepath = os.path.join(REPORTS_TEMP_DIR, filename)
        
        # Save to Excel with basic formatting
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Report Data')
            
            # Auto-adjust columns width
            worksheet = writer.sheets['Report Data']
            for idx, col in enumerate(df.columns):
                # Use .str.len() which handles string conversion and NaNs gracefully
                series = df[col].astype(str)
                data_max_len = series.str.len().max()
                
                # Compare with column header length
                header_len = len(str(col))
                max_len = max(int(data_max_len) if pd.notnull(data_max_len) else 0, header_len) + 2
                
                # column index to letter (handles A-Z, simple version)
                col_letter = chr(65 + idx) if idx < 26 else "A" 
                worksheet.column_dimensions[col_letter].width = min(max_len, 50)
            
            # Add autofilter
            worksheet.auto_filter.ref = worksheet.dimensions

        # --- Step 4: Cache Data ---
        session_data[session_id] = {
            "excel_path": filepath,
            "data": data,
            "generated_at": time.time(),
            "query": user_query,
            "filename": filename
        }
        
        # Generate download link
        download_url = f"http://localhost:8000/reports/download/{filename}"
        hidden_metadata = f"<!-- REPORT_URL: {download_url} | FILENAME: {filename} | TYPE: excel -->"
        
        response_text = f"📊 **Report Compiled Successfully**\n\n"
        response_text += f"I have processed \"{user_query}\" and extracted {len(data)} records from the database.\n\n"
        response_text += f"The full spreadsheet is now available for download in the **Reports Panel** on the right.\n\n"
        response_text += f"Would you like me to generate a visual executive summary of this data? (Reply **'proceed'** or **'generate image'**)\n\n"
        response_text += hidden_metadata
        
        logger.info("Report generated and cached", session_id=session_id, filename=filename)
        
        return {
            "messages": [AIMessage(content=response_text)],
            "next_node": "FINISH"
        }

    except Exception as e:
        logger.error("Error generating Excel", error=str(e))
        return {"messages": [AIMessage(content=f"Error generating Excel file: {str(e)}")]}

