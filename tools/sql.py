"""
SQL Tools for the Data Analyst Agent.
Provides safe, read-only database query execution with AST validation,
automatic row limits, schema inspection, and dashboard metric caching.
"""
import json
from typing import Any, Optional, List
import sqlglot
from sqlglot import exp
from langchain_core.tools import tool

from core.config import settings
from core.schemas import (
    ExecuteQuerySchema,
    CacheMetricSchema,
    ListTablesSchema,
    DescribeTableSchema,
    SearchTranscriptsSchema,
)
from db.client import get_db_connection
from db.schema import get_table_names, get_bcnf_schema, get_table_columns
from core.logger import logger
from core.exceptions import DatabaseQueryError
from services.credit_service import CreditService


from langchain_core.runnables import RunnableConfig

@tool(args_schema=ExecuteQuerySchema)
def execute_read_query(query: str, config: RunnableConfig, user_id: Optional[int] = None, role: str = "USER") -> str:
    """
    Executes a single SELECT SQL query on the project database with strict RBAC enforcement.
    Uses config to automatically retrieve user context if not provided.
    """
    # Prefer values from config if available
    cfg_user_id = config.get("configurable", {}).get("user_id")
    cfg_role = config.get("configurable", {}).get("role", "USER")
    
    actual_user_id = user_id if user_id is not None else cfg_user_id
    actual_role = role if role != "USER" else cfg_role

    if actual_user_id is None:
        return json.dumps({"status": "error", "message": "Security Error: user_id is required for query execution."})

    user_id = actual_user_id
    role = actual_role

    try:
        parsed_statements = sqlglot.parse(query)
    except sqlglot.errors.ParseError as e:
        logger.warning("SQL Parse Error", query=query, error=str(e))
        return json.dumps({"status": "error", "message": f"Invalid SQL syntax: {e}"})

    if not parsed_statements or len(parsed_statements) > 1:
        return json.dumps({"status": "error", "message": "Only single SQL statements allowed."})

    expression = parsed_statements[0]
    if not isinstance(expression, exp.Select):
        return json.dumps({"status": "error", "message": "Only SELECT statements allowed."})

    # --- RBAC Enforcement ---
    SENSITIVE_TABLES = {
        "projects": "user_id",
        "clients": "user_id",
        "chat_threads": "user_id",
        "chat_messages": "thread_id",
        "chat_history": "user_id",
        "access_gaps": "user_id",
        "meeting_transcripts": "project_id",
        "user_credits": "user_id",
        "credit_transactions": "user_id",
        "vendor_bills": "user_id",
        "yearly_closings": "user_id",
    }
    ADMIN_TABLES = {"users", "permissions", "user_permissions", "security_events"}

    for table in expression.find_all(exp.Table):
        table_name = table.name.lower()
        if table_name in ADMIN_TABLES:
            logger.warning("Access to admin table blocked", table=table_name, user_id=user_id)
            return json.dumps({"status": "error", "message": f"Security Error: Access to table '{table_name}' is restricted."})
        
        # Automatic isolation injection for projects, clients, threads
        if table_name in ["projects", "clients", "chat_threads", "chat_history", "access_gaps"]:
            # Check if user_id filter already exists in this scope
            # To be simple and robust, we can use a subquery or just append a global filter
            # But sqlglot allows us to modify the expression
            pass # We'll do a global check below for simplicity in this version

    # Robust approach: Wrap the query in a CTE or a subquery and filter the output
    # if it contains sensitive columns, or better, use sqlglot's optimizer/transformer
    
    # Simpler but very safe approach: 
    # For every sensitive table, we MUST ensure the query filters by user_id.
    # We will modify the AST to append the filter.
    
    def transform_expression(node):
        if isinstance(node, exp.Select):
            # Find all table references in this SELECT
            for table in node.find_all(exp.Table):
                t_name = table.name.lower()
                if t_name in ["projects", "clients", "chat_threads", "chat_history", "access_gaps", "user_credits", "credit_transactions", "vendor_bills", "yearly_closings"]:
                    # Use alias if available, otherwise use table name
                    alias = table.alias if table.alias else t_name
                    node.where(f"{alias}.user_id = {user_id}", copy=False)
        return node

    # Apply transformation (Strict isolation for everyone)
    expression = transform_expression(expression)

    # --- Auto LIMIT guard ---
    if not expression.find(exp.Limit):
        expression = expression.limit(settings.sql_row_limit)

    final_query = expression.sql()

    # --- Execute ---
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(final_query)
            rows = cursor.fetchall()
            data = [dict(row) for row in rows]
            
            logger.info("SQL Query Executed (RBAC Enforced)", query=final_query, user_id=user_id, row_count=len(data))
            
            # Format output compactly for LLM
            if not data:
                return json.dumps({"status": "success", "data": "No matching records found."})
                
            # If large data, truncate rows but show total count
            MAX_ROWS = 50
            is_truncated = len(data) > MAX_ROWS
            display_data = data[:MAX_ROWS]
            
            formatted_lines = []
            if display_data:
                headers = list(display_data[0].keys())
                formatted_lines.append(" | ".join(headers))
                formatted_lines.append("-" * (len(headers) * 10))
                for row in display_data:
                    formatted_lines.append(" | ".join(str(row.get(h, "")) for h in headers))
            
            result_str = "\n".join(formatted_lines)
            if is_truncated:
                result_str += f"\n... (truncated {len(data) - MAX_ROWS} more rows)"

            return json.dumps({"status": "success", "data": result_str, "message": f"Returned {len(data)} rows (Scoped to user {user_id})."})
    except Exception as e:
        # Pass raw SQLite error back to the LLM so it can learn from its mistakes
        error_msg = str(e).replace('"', "'")
        logger.error("SQL Execution Error", query=final_query, error=error_msg)
        return json.dumps({"status": "error", "message": f"SQLite Execution Error: {error_msg}. Check your syntax and table schema."})


@tool(args_schema=ListTablesSchema)
def list_database_tables() -> str:
    """
    Lists all available tables in the project database.
    Excludes administrative and security-related tables.
    """
    try:
        all_tables = get_table_names()
        ADMIN_TABLES = {"users", "permissions", "user_permissions", "security_events"}
        tables = [t for t in all_tables if t.lower() not in ADMIN_TABLES]
        logger.info("Listed database tables (RBAC applied)", count=len(tables))
        return json.dumps({"status": "success", "data": tables, "message": f"Found {len(tables)} accessible tables."})
    except Exception as e:
        logger.error("List tables failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool(args_schema=DescribeTableSchema)
def describe_table_schema(table_name: str) -> str:
    """
    Returns the full CREATE TABLE DDL and column names for a specific table.
    Access to administrative tables is blocked.
    """
    try:
        ADMIN_TABLES = {"users", "permissions", "user_permissions", "security_events"}
        if table_name.lower() in ADMIN_TABLES:
            return json.dumps({"status": "error", "message": f"Access to table '{table_name}' is restricted."})

        ddl = get_bcnf_schema([table_name])
        columns = get_table_columns(table_name)
        if not ddl:
            return json.dumps({"status": "error", "message": f"Table '{table_name}' not found."})
        
        # Extract join keys for the agent
        join_keys = [c for c in columns if c.endswith("_id")]
        foreign_keys = [line.strip() for line in ddl.split("\n") if "FOREIGN KEY" in line.upper()]
        
        logger.info("Described table schema", table=table_name)
        return json.dumps({
            "status": "success",
            "data": {
                "ddl": ddl, 
                "columns": columns,
                "suggested_joins": join_keys,
                "foreign_keys": foreign_keys
            },
            "message": f"Schema for '{table_name}' with {len(columns)} columns. Identified {len(join_keys)} potential join keys."
        })

    except Exception as e:
        logger.error("Describe table failed", table=table_name, error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool(args_schema=CacheMetricSchema)
def cache_dashboard_metric(metric_key: str, status: str, reason: str) -> str:
    """
    Saves a computed project metric to the dashboard_metrics table.

    Input:
        metric_key: Unique identifier (e.g., 'alpha_milestone_risk').
        status: The evaluated status ('At Risk', 'On Track', 'Delayed', etc.).
        reason: Brief justification for the status.

    Output:
        A JSON object confirming the metric was cached.

    Use this after analyzing query results to flag important project insights
    for the executive dashboard.
    """
    try:
        import sqlite3
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO dashboard_metrics (metric_key, status, reason, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(metric_key) DO UPDATE SET
                   status = excluded.status,
                   reason = excluded.reason,
                   updated_at = CURRENT_TIMESTAMP""",
            (metric_key, status, reason)
        )
        conn.commit()
        conn.close()
        logger.info("Dashboard metric cached", metric_key=metric_key, status=status)
        return json.dumps({
            "status": "success",
            "data": {"metric_key": metric_key, "status": status},
            "message": f"Cached metric '{metric_key}' as '{status}'."
        })
    except Exception as e:
        logger.error("Cache metric failed", metric_key=metric_key, error=str(e))
        return json.dumps({"status": "error", "data": None, "message": str(e)})


@tool(args_schema=SearchTranscriptsSchema)
def search_meeting_transcripts(query: str, config: RunnableConfig, user_id: Optional[int] = None, role: str = "USER") -> str:
    """
    Searches meeting transcripts for a specific keyword, person, or topic.
    Returns matching snippets and meeting dates.
    """
    cfg_user_id = config.get("configurable", {}).get("user_id")
    actual_user_id = user_id if user_id is not None else cfg_user_id

    if actual_user_id is None:
        return json.dumps({"status": "error", "message": "user_id required."})
    
    user_id = actual_user_id

    try:
        # We search raw_text for the query. 
        # RBAC: Join with projects to ensure user_id matches (Skip for ADMIN).
        sql = f"""
            SELECT mt.meeting_date, mt.raw_text, p.project_name
            FROM meeting_transcripts mt
            JOIN projects p ON mt.project_id = p.project_id
            WHERE (mt.raw_text LIKE '%{query}%')
        """
        sql += f" AND p.user_id = {user_id}"
        
        sql += " LIMIT 5"
        with get_db_connection(read_only=True) as conn:
            rows = conn.execute(sql).fetchall()
            data = []
            for row in rows:
                text = row["raw_text"]
                idx = text.lower().find(query.lower())
                start = max(0, idx - 150)
                end = min(len(text), idx + 300)
                snippet = text[start:end]
                data.append({
                    "date": row["meeting_date"],
                    "project": row["project_name"],
                    "snippet": f"...{snippet}..."
                })
            
            logger.info("Transcript search completed", query=query, user_id=user_id, count=len(data))
            return json.dumps({"status": "success", "data": data})
    except Exception as e:
        logger.error("Transcript search failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})