"""
Database schema introspection utilities.
Provides DDL extraction and table listing for LLM-powered SQL generation.
"""
import sqlite3
from typing import List
from core.logger import logger
from core.config import settings
from core.exceptions import SchemaIntrospectionError


def get_bcnf_schema(tables: List[str] = None) -> str:
    """
    Extracts exact CREATE TABLE DDL statements from the database.
    The LLM uses these to write precise JOINs and column selections.

    Args:
        tables: Optional list of table names to filter. If None, returns all tables.

    Returns:
        A string containing CREATE TABLE statements separated by double newlines.
    """
    try:
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()

        query = "SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        if tables:
            placeholders = ",".join("?" for _ in tables)
            query += f" AND name IN ({placeholders})"
            cursor.execute(query, tables)
        else:
            cursor.execute(query)

        schemas = cursor.fetchall()
        conn.close()
        return "\n\n".join([row[0] for row in schemas if row[0]])
    except Exception as e:
        logger.error("Schema extraction failed", error=str(e))
        raise SchemaIntrospectionError(f"Failed to read database schema: {e}")


def get_table_names() -> List[str]:
    """
    Retrieves all user-created table names from the database.

    Returns:
        A list of table name strings. Returns empty list on failure.
    """
    try:
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
    except Exception as e:
        logger.error("Table name extraction failed", error=str(e))
        return []


def get_table_columns(table_name: str) -> List[str]:
    """
    Returns the column names for a specific table.

    Args:
        table_name: The exact table name to inspect.

    Returns:
        A list of column name strings.
    """
    try:
        conn = sqlite3.connect(settings.db_path)
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        return columns
    except Exception as e:
        logger.error("Column extraction failed", table=table_name, error=str(e))
        return []