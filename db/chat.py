import sqlite3
from typing import List, Optional, Dict
from db.client import get_db_connection


def create_thread(thread_id: str, user_id: Optional[str] = None) -> None:
    with get_db_connection(read_only=False) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO chat_threads (thread_id, user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (thread_id, user_id),
        )
        conn.commit()


def save_chat_message(thread_id: str, role: str, content: str) -> None:
    create_thread(thread_id)
    with get_db_connection(read_only=False) as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (thread_id, role, content)
            VALUES (?, ?, ?)
            """,
            (thread_id, role, content),
        )
        conn.execute(
            """
            UPDATE chat_threads
            SET updated_at = CURRENT_TIMESTAMP
            WHERE thread_id = ?
            """,
            (thread_id,),
        )
        conn.commit()


def get_chat_history(thread_id: str) -> List[Dict[str, str]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT role, content AS message, created_at AS timestamp
            FROM chat_messages
            WHERE thread_id = ?
            ORDER BY created_at ASC, message_id ASC
            """,
            (thread_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_chat_threads(limit: int = 50) -> List[Dict[str, Optional[str]]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            """
            SELECT
              t.thread_id,
              t.created_at,
              t.updated_at,
              COALESCE(
                (SELECT content FROM chat_messages WHERE thread_id = t.thread_id ORDER BY created_at DESC, message_id DESC LIMIT 1),
                '') AS last_message,
              COALESCE((SELECT COUNT(*) FROM chat_messages WHERE thread_id = t.thread_id), 0) AS message_count
            FROM chat_threads t
            ORDER BY t.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_chat_thread(thread_id: str) -> None:
    with get_db_connection(read_only=False) as conn:
        conn.execute("DELETE FROM chat_messages WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM chat_threads WHERE thread_id = ?", (thread_id,))
        conn.commit()


def thread_exists(thread_id: str) -> bool:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM chat_threads WHERE thread_id = ? LIMIT 1",
            (thread_id,),
        ).fetchone()
    return row is not None
