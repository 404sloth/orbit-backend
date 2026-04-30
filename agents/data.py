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
    
    # Retrieve dynamic schema summary (reduced size for TPM limits)
    table_names = get_table_names()
    tables_list = ", ".join(table_names)

    sys_msg = f"""You are the Data Analyst Agent for an executive project dashboard.
Your job is to answer questions by querying the project database accurately.

SECURITY CONTEXT:
- CURRENT USER: {username} (ID: {user_id}, Role: {role})
- PRIVACY RULE: {"As an ADMIN, you have full access to all projects and data." if role == "ADMIN" else f"You MUST filter all queries to the 'projects', 'clients', 'chat_threads', 'chat_history', 'access_gaps', 'user_credits', and 'credit_transactions' tables by 'user_id = {user_id}'."}
- DATA ISOLATION: {"You can see everything." if role == "ADMIN" else "Never return or query data belonging to other user IDs. If a user asks for data outside their scope, politely state that no such project or client was found."}

MISSION CRITICAL:
1. ALWAYS fetch table names using 'list_database_tables' if you are unsure about the structure.
2. ALWAYS call 'describe_table_schema' for EVERY table in your query BEFORE calling 'execute_read_query'.
3. NEVER assume column names or types. Verify them every time.

DATABASE CONTEXT:
The database contains the following tables: [{tables_list}].


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
- NEVER use placeholders like '[Insert Name]' or '[Insert Credits]'. 
- If a query fails with 'no such column', ALWAYS use 'describe_table_schema' on that table to verify column names.
- If a query returns no data, state clearly: "I searched for X but found no matching records for your account."
- ALWAYS provide the REAL DATA retrieved from the database.



AVAILABLE TOOLS:
1. list_database_tables — Discover all available tables.
2. describe_table_schema — Get DDL and column names for a specific table.
3. execute_read_query — Execute a SELECT query.
4. cache_dashboard_metric — Save an important finding for the dashboard.


STRICT TOOL CALLING RULES:
- Use ONLY standard ASCII straight double-quotes (") for JSON keys and strings.
- NEVER use curly quotes (“ or ”).
- NEVER wrap tool calls in XML-like tags like <function=...>. 
- Ensure all JSON is perfectly formatted.

WORKFLOW (STRICT MULTI-STEP PROCESS):
1. DISCOVERY: If you are unsure which tables to use, ALWAYS call 'list_database_tables' first.
2. INSPECTION: For EVERY table you plan to use in a query (including JOINs), you MUST call 'describe_table_schema' to get the exact column names and FOREIGN KEY constraints. NEVER assume a column exists based on common sense.
3. ANALYSIS: Look for join keys (e.g., project_id, user_id) in the DDL to ensure your JOINs are correct.
4. EXECUTION: Only after you have the verified schema, call 'execute_read_query' with explicit column names.
5. RECOVERY: If a query fails with 'no such column', repeat step 2 for that table.
6. MONITOR: If you find critical/at-risk items, use cache_dashboard_metric to flag them.

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

        # ROOT FIX: Prune messages to stay within Groq TPM limits
        all_messages = state["messages"]
        if len(all_messages) > 12:
            pruned_messages = [all_messages[0]] + list(all_messages[-10:])
        else:
            pruned_messages = list(all_messages)

        # Capture original length BEFORE invocation to avoid mutation bugs
        # We use the length of pruned_messages because that's what the agent executor starts with
        pruned_len = len(pruned_messages)
        result = agent_executor.invoke({"messages": pruned_messages})

        # Return only new messages generated by this agent
        all_messages_after = result["messages"]
        if len(all_messages_after) > pruned_len:
            new_messages = all_messages_after[pruned_len:]
        else:
            # If for some reason it's shorter or same length, assume no new messages
            new_messages = []
        
        logger.info(
            "SQL Agent finished",
            in_count=len(state["messages"]),
            out_count=len(all_messages_after),
            new_count=len(new_messages)
        )
        
        # If the agent produced no new messages, it might be stuck or 
        # think it already answered. Add a fallback message to break loops.
        if not new_messages:
            from langchain_core.messages import SystemMessage
            new_messages = [SystemMessage(content="[SYSTEM] SQL Agent reviewed the history and found no new actions needed.")]

        return {"messages": new_messages}

    except Exception as e:
        logger.exception("SQL Agent execution failed")
        from langchain_core.messages import AIMessage
        err_msg = str(e) if str(e) else repr(e)
        return {
            "messages": [AIMessage(content=f"Data Analyst Error: {err_msg}. Please try rephracing your question.")]
        }