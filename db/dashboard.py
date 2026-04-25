import sqlite3
from typing import List, Dict, Any, Optional
from db.client import get_db_connection

def get_all_projects() -> List[Dict[str, Any]]:
    """
    Fetch all projects with their basic info and SOW dates.
    """
    with get_db_connection() as conn:
        query = """
            SELECT 
                p.project_id as id,
                p.project_name as name,
                p.current_status as status,
                p.created_at,
                s.start_date,
                s.end_date,
                CASE 
                    WHEN p.current_status = 'Completed' THEN 'green'
                    WHEN p.current_status IN ('Active', 'Bidding') THEN 'amber'
                    ELSE 'red'
                END as health_color,
                (
                    SELECT COUNT(*) * 100 / COUNT(*) 
                    FROM milestones m 
                    WHERE m.sow_id = s.sow_id AND m.status = 'Completed'
                ) as progress_percent
            FROM projects p
            LEFT JOIN statements_of_work s ON p.project_id = s.project_id
        """
        rows = conn.execute(query).fetchall()
        
    projects = []
    for row in rows:
        p = dict(row)
        if p['progress_percent'] is None:
            p['progress_percent'] = 0
        projects.append(p)
    return projects

def get_project_timeline(project_id: str) -> List[Dict[str, Any]]:
    """
    Fetch a unified timeline of meetings and milestones for a project.
    """
    timeline = []
    
    with get_db_connection() as conn:
        # Fetch Meetings
        meetings = conn.execute("""
            SELECT 
                'meeting' as type,
                transcript_id as id,
                meeting_date as date,
                meeting_type as title,
                cleaned_summary as summary
            FROM meeting_transcripts
            WHERE project_id = ?
            ORDER BY meeting_date DESC
        """, (project_id,)).fetchall()
        
        for m in meetings:
            timeline.append(dict(m))
            
        # Fetch Milestones with Tasks
        milestones = conn.execute("""
            SELECT 
                'milestone' as type,
                m.milestone_id as id,
                COALESCE(m.actual_delivery_date, m.planned_delivery_date) as date,
                m.milestone_name as title,
                m.description as summary,
                m.status,
                (
                    SELECT GROUP_CONCAT(task_description || '|' || is_completed, '\n')
                    FROM milestone_tasks mt
                    WHERE mt.milestone_id = m.milestone_id
                ) as tasks_raw
            FROM milestones m
            JOIN statements_of_work s ON m.sow_id = s.sow_id
            WHERE s.project_id = ?
            ORDER BY date DESC
        """, (project_id,)).fetchall()
        
        for ms in milestones:
            d = dict(ms)
            if d.get('tasks_raw'):
                tasks = []
                for line in d['tasks_raw'].split('\n'):
                    if '|' in line:
                        desc, done = line.rsplit('|', 1)
                        check = '[x]' if done == '1' else '[ ]'
                        tasks.append(f"{check} {desc}")
                task_list = "\n".join(tasks)
                d['summary'] = (d['summary'] or '') + "\n\nDeliverables:\n" + task_list
            timeline.append(d)
            
    # Sort unified timeline by date descending
    timeline.sort(key=lambda x: x['date'] or '', reverse=True)
    return timeline
