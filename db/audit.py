from typing import List, Dict, Any, Optional
from core.logger import logger
from db.client import get_db_connection

def get_access_gaps(user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Fetches access gaps, optionally filtered by the project owner (user_id).
    """
    try:
        with get_db_connection() as conn:
            query = """
            SELECT 
                ag.gap_id,
                u.username,
                u.role,
                p.project_name,
                perm.permission_name,
                ag.reason,
                ag.severity,
                ag.status,
                ag.last_active
            FROM access_gaps ag
            JOIN users u ON ag.user_id = u.user_id
            JOIN projects p ON ag.project_id = p.project_id
            JOIN permissions perm ON ag.permission_id = perm.permission_id
            """
            params = []
            if user_id is not None:
                # Filter by the user who owns the project or the user who the gap belongs to
                query += " WHERE ag.user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY ag.created_at DESC"
            rows = conn.execute(query, params).fetchall()
        
        gaps = []
        for row in rows:
            username = row[1] or "Unknown"
            # Generate a consistent avatar initial from name
            initials = "".join([n[0] for n in username.split("_") if n]).upper()[:2]
            
            gaps.append({
                "id": str(row[0]),
                "user": {
                    "name": username.replace("_", " ").title(),
                    "role": row[2] or "USER",
                    "avatar": initials or "U"
                },
                "project": row[3] or "Global",
                "permission": row[4] or "General",
                "reason": row[5] or "No reason provided",
                "severity": row[6] or "low",
                "status": row[7] or "flagged",
                "lastActive": row[8] or "Never"
            })
            
        return gaps
    except Exception as e:
        logger.error(f"Failed to fetch access gaps: {e}")
        return []
