"""
Access Manager — Centralized Role-Based Access Control (RBAC) logic.
Provides robust checks for user permissions on various resources.
"""
from typing import List, Optional
from db.client import get_db_connection
from core.logger import logger
from core.exceptions import SecurityError

class AccessManager:
    """Handles all resource-level permission checks."""

    @staticmethod
    def can_access_table(user_id: int, role: str, table_name: str) -> bool:
        """
        Checks if a user has permission to read from a specific table.
        ADMINs can access everything.
        """
        if role == "ADMIN":
            return True

        # Define table-level restrictions
        restricted_tables = ["security_events", "users", "permissions", "user_permissions"]
        if table_name in restricted_tables:
            return False

        # For business tables, we allow access but will enforce row-level filtering in the tool
        return True

    @staticmethod
    def can_access_thread(user_id: int, role: str, thread_id: str) -> bool:
        """Checks if a user owns a chat thread or is an ADMIN."""
        if role == "ADMIN":
            return True

        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM chat_threads WHERE thread_id = ? AND user_id = ?",
                    (thread_id, user_id)
                ).fetchone()
                return row is not None
        except Exception as e:
            logger.error(f"Error checking thread access: {e}")
            return False

    @staticmethod
    def can_access_project(user_id: int, role: str, project_id: int) -> bool:
        """Checks if a user is assigned to a project or is an ADMIN."""
        if role == "ADMIN":
            return True

        try:
            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM projects WHERE project_id = ? AND user_id = ?",
                    (project_id, user_id)
                ).fetchone()
                return row is not None
        except Exception as e:
            logger.error(f"Error checking project access: {e}")
            return False

    @staticmethod
    def get_user_permissions(user_id: int) -> List[str]:
        """Retrieves all named permissions for a user."""
        try:
            with get_db_connection() as conn:
                rows = conn.execute("""
                    SELECT p.permission_name 
                    FROM permissions p
                    JOIN user_permissions up ON p.permission_id = up.permission_id
                    WHERE up.user_id = ?
                """, (user_id,)).fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Error retrieving user permissions: {e}")
            return []

    @staticmethod
    def has_permission(user_id: int, role: str, permission_name: str) -> bool:
        """Checks if a user has a specific granular permission."""
        if role == "ADMIN":
            return True
            
        permissions = AccessManager.get_user_permissions(user_id)
        return permission_name in permissions
