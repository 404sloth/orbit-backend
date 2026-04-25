"""
Budget Tracking Tools for the Budget Agent.
Provides comprehensive budget analysis, forecasting, and cost management.
"""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from langchain_core.tools import tool
from core.config import settings
from core.schemas import ExecuteQuerySchema
from db.client import get_db_connection
from core.logger import logger
from core.formatters import DataFormatter


@tool
def get_project_budget_status(project_id: int) -> str:
    """
    Get comprehensive budget status for a project.
    
    Shows: Total budget, allocated, spent, remaining, burn rate
    
    Input:
        project_id: The project ID to analyze
        
    Output:
        JSON with budget breakdown and status
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            # Get total budget from SOW
            cursor.execute("""
                SELECT 
                    sow.total_budget,
                    sow.start_date,
                    sow.end_date,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN 1 ELSE 0 END) as completed_milestones
                FROM statements_of_work sow
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                WHERE sow.project_id = ?
                GROUP BY sow.sow_id
            """, (project_id,))
            
            result = cursor.fetchone()
            if not result:
                return json.dumps({
                    "status": "error",
                    "message": f"No SOW found for project {project_id}"
                })
            
            total_budget, start_date, end_date, total_milestones, completed_milestones = result
            
            # Get milestone payments
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as paid,
                    SUM(m.payment_amount) as total_milestone_value
                FROM milestones m
                JOIN statements_of_work sow ON m.sow_id = sow.sow_id
                WHERE sow.project_id = ?
            """, (project_id,))
            
            paid_result = cursor.fetchone()
            paid = paid_result[0] or 0
            total_milestone_value = paid_result[1] or 0
            
            # Calculate burn rate
            if start_date:
                start = datetime.fromisoformat(start_date)
                today = datetime.now()
                days_elapsed = max(1, (today - start).days)
                burn_rate = paid / days_elapsed if days_elapsed > 0 else 0
            else:
                burn_rate = 0
            
            # Build response
            remaining = total_budget - paid if total_budget else 0
            percentage_spent = (paid / total_budget * 100) if total_budget else 0
            
            return json.dumps({
                "status": "success",
                "data": {
                    "total_budget": total_budget,
                    "spent": paid,
                    "remaining": remaining,
                    "percentage_spent": round(percentage_spent, 2),
                    "daily_burn_rate": round(burn_rate, 2),
                    "milestones_completed": completed_milestones,
                    "total_milestones": total_milestones,
                    "projected_completion_cost": paid + (total_budget - paid) * (completed_milestones / max(1, total_milestones))
                },
                "message": f"Budget status for project {project_id}"
            })
    except Exception as e:
        logger.error("Budget status query failed", project_id=project_id, error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def find_over_budget_projects() -> str:
    """
    Find all projects that are over budget or at risk of overrun.
    
    Returns projects with:
    - Current spending > allocated budget
    - Projected cost exceeding budget
    - High burn rate relative to timeline
    
    Output:
        JSON list of at-risk projects
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    p.project_id,
                    p.project_name,
                    sow.total_budget,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN 1 ELSE 0 END) as completed_milestones,
                    SUM(m.payment_amount) as total_milestone_value
                FROM projects p
                JOIN statements_of_work sow ON p.project_id = sow.project_id
                JOIN milestones m ON sow.sow_id = m.sow_id
                GROUP BY p.project_id
                HAVING spent > sow.total_budget * 0.9
                ORDER BY (spent / sow.total_budget) DESC
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                return json.dumps({
                    "status": "success",
                    "data": [],
                    "message": "No projects at risk of budget overrun"
                })
            
            projects_at_risk = []
            for row in rows:
                project_id, name, budget, spent, total_m, completed_m, milestone_val = row
                overrun_pct = ((spent - budget) / budget * 100) if budget else 0
                
                projects_at_risk.append({
                    "project_id": project_id,
                    "project_name": name,
                    "budget": budget,
                    "spent": spent,
                    "overrun_amount": spent - budget,
                    "overrun_percentage": round(overrun_pct, 2),
                    "progress": round(completed_m / total_m * 100, 1) if total_m else 0
                })
            
            return json.dumps({
                "status": "success",
                "data": projects_at_risk,
                "message": f"Found {len(projects_at_risk)} projects at budget risk"
            })
    except Exception as e:
        logger.error("Over budget query failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def forecast_budget_completion(project_id: int) -> str:
    """
    Forecast if project will exceed budget based on current burn rate.
    
    Calculates:
    - Projected final cost at current burn rate
    - Days until budget exhausted
    - Recommendation (on track, warning, at risk)
    
    Input:
        project_id: Project to analyze
        
    Output:
        Forecast with recommendation
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    sow.total_budget,
                    sow.start_date,
                    sow.end_date,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN 1 ELSE 0 END) as completed_milestones
                FROM statements_of_work sow
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                WHERE sow.project_id = ?
                GROUP BY sow.sow_id
            """, (project_id,))
            
            result = cursor.fetchone()
            if not result:
                return json.dumps({"status": "error", "message": "Project not found"})
            
            budget, start_date, end_date, spent, total_m, completed_m = result
            spent = spent or 0
            
            # Calculate burn rate
            if start_date:
                start = datetime.fromisoformat(start_date)
                today = datetime.now()
                days_elapsed = max(1, (today - start).days)
                daily_burn = spent / days_elapsed
            else:
                daily_burn = 0
            
            # Project remaining work
            remaining_milestones = total_m - completed_m if total_m else 0
            progress_pct = (completed_m / total_m * 100) if total_m else 0
            
            # Simple projection: if we've spent this much at this progress, project final cost
            if progress_pct > 0:
                projected_cost = (spent / (progress_pct / 100)) if progress_pct > 0 else budget
            else:
                projected_cost = budget
            
            # Get timeline remaining
            if end_date:
                end = datetime.fromisoformat(end_date)
                days_remaining = max(1, (end - today).days)
            else:
                days_remaining = 0
            
            # Forecast
            projected_overrun = projected_cost - budget
            will_overrun = projected_cost > budget
            
            status = "ALERT" if will_overrun else "ON TRACK"
            if will_overrun and abs(projected_overrun) > budget * 0.2:
                status = "CRITICAL"
            
            return json.dumps({
                "status": "success",
                "data": {
                    "current_spent": spent,
                    "budget": budget,
                    "projected_final_cost": round(projected_cost, 2),
                    "projected_overrun": round(projected_overrun, 2),
                    "overrun_percentage": round((projected_overrun / budget * 100), 2) if budget else 0,
                    "progress_percentage": round(progress_pct, 1),
                    "daily_burn_rate": round(daily_burn, 2),
                    "days_remaining": days_remaining,
                    "forecast_status": status,
                    "recommendation": "REDUCE SCOPE" if will_overrun and abs(projected_overrun) > budget * 0.15 else "MONITOR CLOSELY" if will_overrun else "ON TRACK"
                },
                "message": f"Budget forecast for project {project_id}"
            })
    except Exception as e:
        logger.error("Budget forecast failed", project_id=project_id, error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def analyze_cost_by_milestone(project_id: int) -> str:
    """
    Break down project costs by milestone to identify expense patterns.
    
    Shows: Planned cost per milestone, actual cost, variance
    
    Input:
        project_id: Project to analyze
        
    Output:
        Cost breakdown by milestone
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    m.milestone_name,
                    m.payment_amount,
                    m.status,
                    m.planned_delivery_date,
                    m.actual_delivery_date,
                    CASE 
                        WHEN m.status = 'Completed' THEN m.payment_amount
                        WHEN m.status = 'In-Progress' THEN m.payment_amount * 0.5
                        ELSE 0
                    END as projected_cost
                FROM milestones m
                JOIN statements_of_work sow ON m.sow_id = sow.sow_id
                WHERE sow.project_id = ?
                ORDER BY m.milestone_id
            """, (project_id,))
            
            rows = cursor.fetchall()
            
            if not rows:
                return json.dumps({
                    "status": "error",
                    "message": f"No milestones found for project {project_id}"
                })
            
            milestones = []
            total_planned = 0
            total_spent = 0
            
            for row in rows:
                name, amount, status, planned_date, actual_date, projected = row
                total_planned += amount or 0
                total_spent += projected or 0
                
                variance = amount - projected if amount else 0
                
                milestones.append({
                    "milestone": name,
                    "planned_amount": amount,
                    "actual_spent": projected,
                    "variance": variance,
                    "status": status,
                    "planned_date": planned_date,
                    "actual_date": actual_date or "Not yet completed"
                })
            
            return json.dumps({
                "status": "success",
                "data": {
                    "milestones": milestones,
                    "total_planned": total_planned,
                    "total_spent": total_spent,
                    "total_variance": total_planned - total_spent
                },
                "message": f"Cost analysis for {len(milestones)} milestones"
            })
    except Exception as e:
        logger.error("Cost by milestone query failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def compare_bid_vs_actual(project_id: int) -> str:
    """
    Compare original vendor bid vs actual spending.
    
    Shows: Bid amount, actual spent, variance, percentage overrun
    
    Input:
        project_id: Project to analyze
        
    Output:
        Bid vs actual comparison
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    p.project_name,
                    v.vendor_name,
                    vb.proposed_budget as bid_amount,
                    sow.total_budget as actual_budget,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent,
                    vb.bid_status
                FROM projects p
                JOIN vendor_bids vb ON p.project_id = vb.rfp_id OR vb.bid_status = 'Won'
                JOIN statements_of_work sow ON p.project_id = sow.project_id
                JOIN vendors v ON sow.vendor_id = v.vendor_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                WHERE p.project_id = ?
                GROUP BY sow.sow_id
            """, (project_id,))
            
            rows = cursor.fetchall()
            
            if not rows:
                return json.dumps({
                    "status": "error",
                    "message": "No bid information found"
                })
            
            comparisons = []
            for row in rows:
                proj_name, vendor, bid, actual_budget, spent, status = row
                spent = spent or 0
                
                bid_variance = actual_budget - bid if bid else 0
                bid_variance_pct = (bid_variance / bid * 100) if bid else 0
                spend_variance = spent - bid if bid else 0
                
                comparisons.append({
                    "project": proj_name,
                    "vendor": vendor,
                    "bid_amount": bid,
                    "actual_budget": actual_budget,
                    "bid_variance": bid_variance,
                    "bid_variance_percentage": round(bid_variance_pct, 2),
                    "currently_spent": spent,
                    "spend_variance": spend_variance,
                    "bid_status": status
                })
            
            return json.dumps({
                "status": "success",
                "data": comparisons,
                "message": "Bid vs actual comparison"
            })
    except Exception as e:
        logger.error("Bid vs actual query failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})
