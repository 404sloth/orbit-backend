"""
Background Schema Cache Service
Periodically caches database schema to avoid expensive LLM tool calls.
"""
import asyncio
from typing import Dict, Any
from core.logger import logger
from db.schema import get_table_names, get_table_columns

# Global in-memory cache
_SCHEMA_CACHE: Dict[str, Any] = {
    "tables_csv": "",
    "detailed_schema": "",
    "last_updated": None
}

def get_cached_schema() -> Dict[str, Any]:
    """Returns the globally cached schema information."""
    return _SCHEMA_CACHE

def update_schema_cache():
    """Fetches schema from database and updates the global cache."""
    try:
        table_names = get_table_names()
        # Filter out admin tables
        ADMIN_TABLES = {"users", "permissions", "user_permissions", "security_events"}
        safe_tables = [t for t in table_names if t.lower() not in ADMIN_TABLES]
        
        detailed = []
        for table in safe_tables:
            columns = get_table_columns(table)
            col_str = ", ".join(columns)
            detailed.append(f"- {table}: [{col_str}]")
        
        _SCHEMA_CACHE["tables_csv"] = ", ".join(safe_tables)
        _SCHEMA_CACHE["detailed_schema"] = "\n".join(detailed)
        _SCHEMA_CACHE["last_updated"] = asyncio.get_event_loop().time()
        logger.info("Schema cache updated successfully in background.")
    except Exception as e:
        logger.error(f"Failed to update schema cache: {e}")

async def schema_cache_task():
    """Background task that runs every 5 minutes to keep the schema fresh."""
    while True:
        try:
            update_schema_cache()
        except Exception as e:
            logger.error(f"Error in schema cache loop: {e}")
        
        # Wait 5 minutes (300 seconds)
        await asyncio.sleep(300)
