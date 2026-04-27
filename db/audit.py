import sqlite3
from typing import List, Dict, Any
from core.config import settings
from core.logger import logger

def get_access_gaps() -> List[Dict[str, Any]]:
    """
    Fetches all access gaps from the database with joined user, project, and permission details.
    Normalized BCNF schema requires JOINs to reconstruct the frontend model.
    """
    try:
        conn = sqlite3.connect(settings.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
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
        ORDER BY ag.created_at DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        gaps = []
        for row in rows:
            # Generate a consistent avatar initial from name
            initials = "".join([n[0] for n in row[1].split("_") if n]).upper()[:2]
            
            gaps.append({
                "id": str(row[0]),
                "user": {
                    "name": row[1].replace("_", " ").title(),
                    "role": row[2],
                    "avatar": initials
                },
                "project": row[3],
                "permission": row[4],
                "reason": row[5],
                "severity": row[6],
                "status": row[7],
                "lastActive": row[8]
            })
            
        conn.close()
        return gaps
    except Exception as e:
        logger.error(f"Failed to fetch access gaps: {e}")
        return []
