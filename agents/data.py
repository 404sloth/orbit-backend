"""
Data Analyst Agent — Handles all structured database queries.
Uses create_react_agent for multi-step tool reasoning with automatic
tool calling loops. Generates its own subgraph diagram.
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
)
from services.schema_cache import get_cached_schema


def sql_node(state: GraphState, config: RunnableConfig) -> dict:
    """
    Data Analyst sub-agent node. Builds a ReAct agent with SQL tools
    and invokes it on the current conversation state.

    Steps:
    1. Dynamically fetches current database schema.
    2. Creates a ReAct agent with all SQL tools.
    3. Executes the agent and returns only new messages.
    """
    llm = get_llm(temperature=0)
    tools = [
        execute_read_query,
        list_database_tables,
        describe_table_schema,
        cache_dashboard_metric,
    ]


    # Retrieve user context from config
    user_id = config.get("configurable", {}).get("user_id", "Unknown")
    username = config.get("configurable", {}).get("username", "Executive")
    role = config.get("configurable", {}).get("role", "USER")
    
    # Retrieve background cached schema
    cached_schema = get_cached_schema()
    tables_list = cached_schema.get("tables_csv", "")
    detailed_schema = cached_schema.get("detailed_schema", "No details available.")

    sys_msg = f"""You are the Data Analyst Agent for an executive project dashboard.
Your job is to answer questions by querying the project database accurately.

SECURITY CONTEXT:
- CURRENT USER: {username} (ID: {user_id}, Role: {role})
- PRIVACY RULE: You MUST filter all queries to the 'projects', 'clients', 'chat_threads', 'chat_history', 'access_gaps', 'user_credits', and 'credit_transactions' tables by 'user_id = {user_id}'.
- DATA ISOLATION: Never return or query data belonging to other user IDs. If a user asks for data outside their scope, politely state that no such project or client was found for their account.

MISSION CRITICAL:
1. You have been provided the database schema below. Use it to construct your queries directly.
2. Only call 'describe_table_schema' if you get a SQL error and need more details about foreign keys.
3. NEVER assume column names or types not listed in the schema.

DATABASE SCHEMA:
The database contains the following tables: [{tables_list}].
Here are the columns for each table:
{detailed_schema}


CORE TABLES & SCHEMA MAP:
- projects: [project_id, project_name, current_status, user_id] (Filters: user_id)
- user_credits: [user_id, yearly_allocation, used_credits, remaining_credits, financial_year] (Filters: user_id)
- credit_transactions: [user_id, project_id, task_name, credits_used, source_type, timestamp] (Filters: user_id. Joins: projects on project_id)
- milestones: [milestone_id, milestone_name, status, planned_delivery_date] (Joins: projects via statements_of_work)

COMMON COLUMN MAPPINGS:
- If asked for "status", use "current_status" in the 'projects' table.
- If asked for "credits" or "balance", use "remaining_credits" in the 'user_credits' table.
- 'user_credits' DOES NOT have a 'project_id' column.

CORE DOMAIN KNOWLEDGE - CREDIT POOL:
- POOL CONCEPT: Clients pay an annual amount per agreement. This forms a "Pool" for the financial year.
- ROLLOVER: Unused funds from one financial year are carried forward to the next as "Rollover Credits".
- SPENDING PRIORITY: Rollover credits are ALWAYS used first for any project task. Once rollover is exhausted, the current year's allocation is used.
- TRACING: The 'credit_transactions' table's 'details' column contains a trace of which pool (Rollover vs. Current Year) was used for each deduction.
- BILLING: Vendor bills are offset by available credits in the pool before generating a payable amount.

STRICT RESPONSE RULES:
- Professional, executive-grade responses only.
- ALWAYS present data in a clean Markdown TABLE if you find more than one record.
- NEVER use ASCII dividers or decorative lines like '======' or '------'. They break the UI.
- DO NOT mention technical details like "filtering by user_id" or "restricted tables" unless a query actually fails.
- If you find data, show it immediately.
- Use bold headers for key metrics.
- NEVER use placeholders like '[Insert Name]'. 
- If a query fails with 'no such column', ALWAYS use 'describe_table_schema'.
- If a query returns no data, state clearly: "No matching records found for your account."



AVAILABLE TOOLS:
1. list_database_tables — Discover all available tables.
2. describe_table_schema — Get DDL and column names for a specific table.
3. execute_read_query — Execute a SELECT query.
4. cache_dashboard_metric — Save an important finding for the dashboard.


STRICT TOOL CALLING RULES:
- Use ONLY standard ASCII straight double-quotes (") for JSON keys and strings.
- NEVER use curly quotes (“ or ”).
- NEVER wrap tool calls in XML-like tags like <function=...>. RESTRICTIONS:
- DO NOT attempt to query the 'users', 'permissions', or 'security_events' tables. They are restricted for security reasons.
- All your queries will be automatically filtered by 'user_id' for the current user.

WORKFLOW (STRICT MULTI-STEP PROCESS):
1. DISCOVERY: Look at the DATABASE SCHEMA above. 
2. EXECUTION: Call 'execute_read_query' with explicit column names. PREFER 'LEFT JOIN' over inner joins to ensure project data is returned even if related tables (like credits) are empty.
3. PARTIAL RESULTS: If a complex join returns no data, RE-TRY with a simpler query on just the primary table (e.g., 'projects') to ensure the user gets at least basic information.
4. RECOVERY: If a query fails with 'no such column', call 'describe_table_schema'.
5. MONITOR: If you find critical items, use cache_dashboard_metric.
"""

    try:
        agent_executor = create_react_agent(llm, tools, state_modifier=sys_msg)

        # Save subgraph diagram
        try:
            out_dir = pathlib.Path("graph_img")
            out_dir.mkdir(exist_ok=True)
            with open(out_dir / "sql_agent_latest.png", "wb") as f:
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

        # Capture original length BEFORE invocation to avoid mutation bugs
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
        
        if not new_messages:
            # Fallback if no AI message was produced
            from langchain_core.messages import SystemMessage
            new_messages = [SystemMessage(content="[SYSTEM] SQL Agent reviewed the data but produced no final summary.")]

        return {"messages": new_messages}

    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.exception("SQL Agent execution failed")
        from langchain_core.messages import AIMessage
        err_msg = str(e) if str(e) else repr(e)
        return {
            "messages": [AIMessage(content=f"Data Analyst Error: {err_msg}. Please try rephracing your question.")]
        }