"""
Strategic Intelligence Agent — Combined specialist for SQL and RAG analysis.
Handles complex queries that require both structured data and unstructured context.
"""
import pathlib
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage
from core.factory import get_llm
from core.state import GraphState
from core.logger import logger
from db.schema import get_bcnf_schema, get_table_names
from tools.sql import (
    execute_read_query,
    list_database_tables,
    describe_table_schema,
    cache_dashboard_metric,
)
from tools.rag import search_project_documents

def hybrid_node(state: GraphState) -> dict:
    """
    Strategic Intelligence sub-agent node.
    Combines SQL and RAG tools for joint analysis.
    """
    llm = get_llm(temperature=0)
    tools = [
        execute_read_query,
        list_database_tables,
        describe_table_schema,
        cache_dashboard_metric,
        search_project_documents,
    ]

    # Retrieve dynamic schema context for SQL
    table_names = get_table_names()
    schema_context = get_bcnf_schema(table_names)

    sys_msg = f"""You are the Strategic Intelligence Agent for an executive dashboard.
Your job is to provide deep, comprehensive answers by combining structured data (SQL) 
with unstructured context (RAG/Meeting Transcripts).

DATABASE SCHEMA (SQL):
{schema_context}

AVAILABLE TOOLS:
1. SQL: list_database_tables, describe_table_schema, execute_read_query.
2. RAG: search_project_documents.
3. DASHBOARD: cache_dashboard_metric (use to flag critical risks/milestones).

WORKFLOW:
1. JOINT ANALYSIS: For any question about "status" or "meetings", use BOTH sources.
   - Use SQL to get the latest numbers, dates, and milestone names.
   - Use RAG to get the discussion points, reasoning, and context from transcripts.
2. SYNTHESIZE: Combine the findings into a single informative response. 
   - e.g., "SQL shows project X is at 50% budget, but the latest meeting transcript (RAG) indicates a delay due to..."
3. BE INFORMATIVE: Don't just give raw data. Provide executive-level insights.
4. CITE SOURCES: Mention the tables or document sources explicitly.

RULES:
- NEVER assume data. If it's not in SQL or RAG, say so.
- Always name SQL columns explicitly.
- If you find no new actions to take, you MUST finish.
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

        # Prune messages to stay within token limits
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
        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content=f"Strategic Intelligence Error: {str(e)}. Please try rephrasing.")]
        }
