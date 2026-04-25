"""
SQL Tools for the Data Analyst Agent.
Provides safe, read-only database query execution with AST validation,
automatic row limits, schema inspection, and dashboard metric caching.
"""
import json
from typing import Any
import sqlglot
from sqlglot import exp
from langchain_core.tools import tool

from core.config import settings
from core.schemas import (
    ExecuteQuerySchema,
    CacheMetricSchema,
    ListTablesSchema,
    DescribeTableSchema,
)
from db.client import get_db_connection
from db.schema import get_table_names, get_bcnf_schema, get_table_columns
from core.logger import logger
from core.exceptions import DatabaseQueryError


@tool(args_schema=ExecuteQuerySchema)
def execute_read_query(query: str) -> str:
    """
    Executes a single SELECT SQL query on the project database.

    Input:
        query: A valid SQL SELECT statement with explicit column names.

    Output:
        A JSON array of row objects on success (e.g., [{"col": "val"}, ...]).
        An error string prefixed with 'ERROR:' or 'SQL_ERROR:' on failure.

    Security:
        - Only single SELECT statements are allowed (enforced via AST parsing).
        - DROP, DELETE, UPDATE, INSERT are all blocked.
        - Automatic LIMIT is appended if missing to prevent context overflow.
    """
    # --- AST Validation ---
    try:
        parsed_statements = sqlglot.parse(query)
    except sqlglot.errors.ParseError as e:
        logger.warning("SQL Parse Error", query=query, error=str(e))
        return json.dumps({"status": "error", "data": None, "message": f"Invalid SQL syntax: {e}"})

    if not parsed_statements or len(parsed_statements) > 1:
        logger.warning("SQL Multiple Statements Blocked", query=query)
        return json.dumps({"status": "error", "data": None, "message": "Only single SQL statements allowed."})

    root_node = parsed_statements[0]
    if not isinstance(root_node, exp.Select):
        logger.warning("SQL Non-Select Blocked", query=query, type=type(root_node).__name__)
        return json.dumps({"status": "error", "data": None, "message": "Only SELECT statements allowed."})

    # --- Auto LIMIT guard ---
    if not root_node.find(exp.Limit):
        query = f"{query.rstrip().rstrip(';')} LIMIT {settings.sql_row_limit}"

    # --- Execute ---
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            data = [dict(row) for row in rows]
            logger.info("SQL Query Executed", query=query, row_count=len(data))
            return json.dumps({"status": "success", "data": data, "message": f"Returned {len(data)} rows."})
    except Exception as e:
        logger.error("SQL Execution Error", query=query, error=str(e))
        return json.dumps({"status": "error", "data": None, "message": f"SQL_ERROR: {str(e)}"})


@tool(args_schema=ListTablesSchema)
def list_database_tables() -> str:
    """
    Lists all available tables in the project database.

    Input: None required.

    Output:
        A JSON object with status and a list of table names.

    Use this FIRST when you need to discover what data is available
    before writing a query.
    """
    try:
        tables = get_table_names()
        logger.info("Listed database tables", count=len(tables))
        return json.dumps({"status": "success", "data": tables, "message": f"Found {len(tables)} tables."})
    except Exception as e:
        logger.error("List tables failed", error=str(e))
        return json.dumps({"status": "error", "data": None, "message": str(e)})


@tool(args_schema=DescribeTableSchema)
def describe_table_schema(table_name: str) -> str:
    """
    Returns the full CREATE TABLE DDL and column names for a specific table.

    Input:
        table_name: The exact name of the table to inspect.

    Output:
        A JSON object containing the DDL schema string and column list.

    Use this to understand column names, types, and foreign key relationships
    BEFORE writing a query.
    """
    try:
        ddl = get_bcnf_schema([table_name])
        columns = get_table_columns(table_name)
        if not ddl:
            return json.dumps({"status": "error", "data": None, "message": f"Table '{table_name}' not found."})
        logger.info("Described table schema", table=table_name)
        return json.dumps({
            "status": "success",
            "data": {"ddl": ddl, "columns": columns},
            "message": f"Schema for '{table_name}' with {len(columns)} columns."
        })
    except Exception as e:
        logger.error("Describe table failed", table=table_name, error=str(e))
        return json.dumps({"status": "error", "data": None, "message": str(e)})


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