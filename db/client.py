import sqlite3
from contextlib import contextmanager
from typing import Generator
from core.config import settings

@contextmanager
def get_db_connection(read_only: bool = True) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for safe SQLite connections.
    Usage:
        with get_db_connection() as conn:
            conn.execute(...)
    """
    # Force read-only mode if requested using connection URI formatting
    if read_only:
        db_uri = f"file:{settings.db_path}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
    else:
        conn = sqlite3.connect(settings.db_path)
        
    conn.row_factory = sqlite3.Row
        
    try:
        yield conn
    finally:
        conn.close()