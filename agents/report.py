"""
Report Agent - Handles Excel and PDF generation.
Refactored as a ReAct agent for multi-tool orchestration.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from db.schema import get_bcnf_schema, get_table_names
from tools.sql import execute_read_query
from tools.document import generate_executive_report

def report_node(state: GraphState) -> dict:
    """
    Report Agent node. Uses ReAct agent to decide between 
    SQL queries and PDF document generation.
    """
    llm = get_llm(temperature=0)
    tools = [
        execute_read_query,
        generate_executive_report,
    ]

    # Retrieve dynamic schema context
    table_names = get_table_names()
    schema_context = get_bcnf_schema(table_names)



    sys_msg = f"""You are the Executive Report Agent. 
Your job is to generate professional documents (PDF, DOCX) or data spreadsheets (Excel).

CAPABILITIES:
1. SQL: Use execute_read_query to fetch data from the database.
2. DOCUMENTS: Use generate_executive_report to create premium summaries, RFPs, SOWs, or spreadsheets.

DATABASE SCHEMA:
{schema_context}

STRICT TOOL CALLING RULES:
- Use ONLY standard ASCII straight double-quotes (") for JSON keys and strings.
- NEVER use curly quotes (“ or ”).
- NEVER wrap tool calls in XML-like tags like <function=...>. 
- Ensure all JSON is perfectly formatted.

WORKFLOW:
1. DATA FOCUS: If the user wants a data export or spreadsheet, use format='EXCEL'.
2. DOCUMENT FOCUS: Use format='PDF' (default) or 'DOCX' as needed.
3. For PDF/DOCX, provide RICH and DETAILED content_markdown.

RULES:
- DO NOT generate or show download links in your response. The system handles it.
- Include executive summaries, key findings, and action items.
- Keep your confirmation concise and professional.
"""

    try:
        agent_executor = create_react_agent(llm, tools, state_modifier=sys_msg)

        # Prune messages
        all_messages = state["messages"]
        if len(all_messages) > 12:
            pruned_messages = [all_messages[0]] + list(all_messages[-10:])
        else:
            pruned_messages = list(all_messages)

        pruned_len = len(pruned_messages)
        result = agent_executor.invoke({"messages": pruned_messages})

        # Return only new messages
        all_messages_after = result["messages"]
        if len(all_messages_after) > pruned_len:
            new_messages = all_messages_after[pruned_len:]
        else:
            new_messages = []
        
        logger.info(
            "Report Agent finished",
            in_count=len(state["messages"]),
            new_count=len(new_messages)
        )
        
        return {"messages": new_messages}

    except Exception as e:
        logger.exception("Report Agent failed")
        from langchain_core.messages import AIMessage
        err_msg = str(e) if str(e) else repr(e)
        return {
            "messages": [AIMessage(content=f"Report Agent Error: {err_msg}")]
        }
