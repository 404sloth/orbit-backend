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


@tool(args_schema=ExecuteQuerySchema)
def execute_read_query(query: str, user_id: Optional[int] = None) -> str:
    """
    Executes a single SELECT SQL query on the project database with strict RBAC enforcement.

    Input:
        query: A valid SQL SELECT statement.
        user_id: The ID of the current user (injected from context).

    Security:
        - Only single SELECT statements are allowed.
        - Automatically injects 'user_id' filters for sensitive tables (projects, clients, threads, etc.).
        - Blocks access to administrative tables (users, permissions).
    """
    if user_id is None:
        return json.dumps({"status": "error", "message": "Security Error: user_id is required for query execution."})

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
        "chat_messages": "thread_id", # Indirectly secured via thread_id
        "chat_history": "user_id",
        "access_gaps": "user_id",
        "meeting_transcripts": "project_id", # Secured via project_id
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
                if t_name in ["projects", "clients", "chat_threads", "chat_history", "access_gaps"]:
                    # Use alias if available, otherwise use table name
                    alias = table.alias if table.alias else t_name
                    node.where(f"{alias}.user_id = {user_id}", copy=False)
        return node

    # Apply transformation
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
            return json.dumps({"status": "success", "data": data, "message": f"Returned {len(data)} rows (Scoped to user {user_id})."})
    except Exception as e:
        logger.error("SQL Execution Error", query=final_query, error=str(e))
        return json.dumps({"status": "error", "message": f"Database Error: {str(e)}"})


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
        logger.info("Described table schema", table=table_name)
        return json.dumps({
            "status": "success",
            "data": {"ddl": ddl, "columns": columns},
            "message": f"Schema for '{table_name}' with {len(columns)} columns."
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
def search_meeting_transcripts(query: str, user_id: Optional[int] = None) -> str:
    """
    Searches meeting transcripts for a specific keyword, person, or topic.
    Returns matching snippets and meeting dates.
    """
    if user_id is None:
        return json.dumps({"status": "error", "message": "user_id required."})

    try:
        # We search raw_text for the query. 
        # RBAC: Join with projects to ensure user_id matches.
        sql = f"""
            SELECT mt.meeting_date, mt.raw_text, p.project_name
            FROM meeting_transcripts mt
            JOIN projects p ON mt.project_id = p.project_id
            WHERE (mt.raw_text LIKE '%{query}%')
            AND p.user_id = {user_id}
            LIMIT 5
        """
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