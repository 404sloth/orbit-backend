"""
Strategic Intelligence Agent — Combined specialist for SQL and RAG analysis.
Handles complex queries that require both structured data and unstructured context.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from langchain_core.runnables import RunnableConfig
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from db.schema import get_bcnf_schema, get_table_names
from tools.sql import (
    execute_read_query,
    list_database_tables,
    describe_table_schema,
    cache_dashboard_metric,
    search_meeting_transcripts,
)
from tools.rag import search_project_documents
from tools.document import generate_executive_report
from tools.knowledge_search import hybrid_knowledge_search

from langchain_core.messages import AIMessage, SystemMessage

def hybrid_node(state: GraphState, config: RunnableConfig) -> dict:
    """
    Strategic Intelligence sub-agent node.
    Combines SQL, RAG, and Document Generation tools.
    """
    llm = get_llm(temperature=0)
    tools = [
        execute_read_query,
        list_database_tables,
        describe_table_schema,
        cache_dashboard_metric,
        search_project_documents,
        generate_executive_report,
        hybrid_knowledge_search,
        search_meeting_transcripts,
    ]

    # Retrieve dynamic schema summary (reduced size for TPM limits)
    table_names = get_table_names()
    tables_list = ", ".join(table_names)

    user_id = config.get("configurable", {}).get("user_id")
    username = config.get("configurable", {}).get("username", "Executive")
    role = config.get("configurable", {}).get("role", "USER")

    sys_msg = f"""You are the Strategic Intelligence Agent for an executive dashboard.
Your job is to provide deep, human-like, and comprehensive insights by combining structured data (SQL) with unstructured context (RAG/Meeting Transcripts).

PERSONALITY & TONE:
- You are an elite Chief of Staff. Be professional, proactive, and concise.
- Use natural language, contractions, and varied sentence structure. Avoid sounding like a template.
- If you find contradictory information between a database and a transcript, highlight it as a potential risk.

SECURITY CONTEXT:
- CURRENT USER: {username} (ID: {user_id}, Role: {role})
- PRIVACY RULE: You MUST filter all queries to 'projects' and 'clients' by 'user_id = {user_id}'.
- DATA ISOLATION: Never reveal or query data belonging to other user IDs.

DATABASE CONTEXT:
Tables: [{tables_list}]. Use 'describe_table_schema' FIRST to understand columns.

STRICT TOOL CALLING RULES:
- Use ONLY standard ASCII straight double-quotes (") for JSON keys and strings.
- NEVER use curly quotes (“ or ”).
- NEVER wrap tool calls in XML-like tags like <function=...>. 
- Call tools ONE AT A TIME. Do not attempt parallel tool calling.
- Ensure all JSON is perfectly formatted.

AVAILABLE TOOLS:
1. SQL: execute_read_query (Focus on metrics: budget, dates, status).
2. RAG: search_project_documents (Focus on context: notes, RFPs, documents).
3. TRANSCRIPTS: search_meeting_transcripts (Focus on PEOPLE: "What did X say?", "Search discussions about Y").
4. HYBRID: hybrid_knowledge_search (PREFER THIS for general discovery).
5. DASHBOARD: cache_dashboard_metric (Pin critical findings to the Insight panel).
6. DOCUMENTS: generate_executive_report (Create formal summaries/PDFs).

WORKFLOW:
1. DISCOVERY: If the query is broad, start with 'hybrid_knowledge_search'.
2. INSPECTION: For SQL, you MUST call 'describe_table_schema' for candidate tables.
3. INVESTIGATE: If a PERSON is mentioned, use 'search_meeting_transcripts'.
4. SYNTHESIZE: Combine SQL metrics with RAG context. Explain WHY they matter.
5. REPORT: If the user explicitly asks for a PDF or formal document, use 'generate_executive_report'.
6. FINALIZE: Present your findings in a professional, executive-grade summary.
   - NEVER use ASCII dividers like '======' or '------'.
   - Use standard Markdown tables for data.
"""


    try:
        agent_executor = create_react_agent(llm, tools, state_modifier=sys_msg)

        # Save subgraph diagram
        try:
            out_dir = pathlib.Path("graph_img")
            out_dir.mkdir(exist_ok=True)
            with open(out_dir / "hybrid_agent_latest.png", "wb") as f:
                f.write(agent_executor.get_graph().draw_mermaid_png())
        except Exception:
            pass

        # Filter for standard messages to ensure LLM compatibility (especially for Groq)
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
        raw_messages = state.get("messages", [])
        pruned_messages = [
            m for m in raw_messages 
            if isinstance(m, (HumanMessage, AIMessage, SystemMessage, ToolMessage))
        ]

        pruned_len = len(pruned_messages)
        result = agent_executor.invoke({"messages": pruned_messages}, config=config)

        # Return only new AI messages to keep the global state clean
        all_messages_after = result["messages"]
        new_messages = []
        if len(all_messages_after) > pruned_len:
            # Only keep the FINAL response to avoid dangly tool_call metadata
            from langchain_core.messages import AIMessage
            final_msg = all_messages_after[-1]
            if isinstance(final_msg, AIMessage):
                clean_m = AIMessage(content=final_msg.content)
                new_messages.append(clean_m)
        
        logger.info(
            "Strategic Intelligence Agent finished",
            in_count=len(state["messages"]),
            out_count=len(all_messages_after),
            new_count=len(new_messages)
        )
        
        if not new_messages:
            new_messages = [SystemMessage(content="[SYSTEM] Strategic Intelligence Agent found no new actions needed.")]

        return {"messages": new_messages}

    except Exception as e:
        logger.exception("Strategic Intelligence Agent failed")
        err_msg = str(e) if str(e).strip() else repr(e)
        return {
            "messages": [AIMessage(content=f"Strategic Intelligence Error: {err_msg}. Please try rephrasing.")]
        }
