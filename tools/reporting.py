"""
Reporting Tools for the Reports Agent.
Generates executive-ready reports and summaries.
"""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from langchain_core.tools import tool
from db.client import get_db_connection
from core.logger import logger
from services.credit_service import CreditService


@tool
def generate_executive_summary(time_period_days: int = 30, user_id: Optional[int] = None) -> str:
    """
    Generate executive summary for the specified time period.
    
    Includes:
    - Portfolio health overview
    - Key metrics and KPIs
    - Risk summary
    - Recommended actions
    
    Input:
        time_period_days: Number of days to look back (default 30)
        
    Output:
        Executive summary report
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            # Get portfolio metrics
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT p.project_id) as total_projects,
                    SUM(CASE WHEN p.current_status = 'Active' THEN 1 ELSE 0 END) as active_projects,
                    SUM(CASE WHEN p.current_status = 'Completed' THEN 1 ELSE 0 END) as completed_projects,
                    SUM(sow.total_budget) as total_budget,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as total_spent,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN 1 ELSE 0 END) as completed_milestones,
                    SUM(CASE WHEN m.status = 'Delayed' THEN 1 ELSE 0 END) as delayed_milestones
                FROM projects p
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
            """)
            
            result = cursor.fetchone()
            total_proj, active_proj, completed_proj, total_budget, total_spent, total_m, completed_m, delayed_m = result
            
            total_budget = total_budget or 0
            total_spent = total_spent or 0
            
            # Get recent activities
            cursor.execute("""
                SELECT 
                    'Milestone Completed' as activity_type,
                    milestone_name as description,
                    actual_delivery_date as activity_date
                FROM milestones
                WHERE actual_delivery_date >= date('now', ? || ' days')
                
                UNION ALL
                
                SELECT 
                    'Project Created',
                    project_name,
                    created_at
                FROM projects
                WHERE created_at >= date('now', ? || ' days')
                
                ORDER BY activity_date DESC
                LIMIT 10
            """, (f'-{time_period_days}', f'-{time_period_days}'))
            
            activities = [{"type": row[0], "description": row[1], "date": row[2]} for row in cursor.fetchall()]
            
            # Calculate health metrics
            completion_pct = (completed_m / total_m * 100) if total_m else 0
            spend_pct = (total_spent / total_budget * 100) if total_budget else 0
            delay_pct = (delayed_m / total_m * 100) if total_m else 0
            
            # Determine health status
            if delay_pct > 20 or spend_pct > 90:
                health = "AT RISK"
            elif delay_pct > 10 or spend_pct > 75:
                health = "CAUTION"
            else:
                health = "HEALTHY"
            
            # Key findings
            findings = []
            findings.append(f"Portfolio includes {total_proj} projects ({active_proj} active, {completed_proj} completed)")
            findings.append(f"Overall progress: {completion_pct:.1f}% complete ({completed_m}/{total_m} milestones)")
            findings.append(f"Budget status: {spend_pct:.1f}% spent (${total_spent:,.0f} of ${total_budget:,.0f})")
            if delayed_m > 0:
                findings.append(f"Timeline: {delayed_m} milestones delayed ({delay_pct:.1f}%)")
            
            # Recommendations
            recommendations = []
            if spend_pct > 85:
                recommendations.append("Review budget utilization - consider scope adjustments")
            if delay_pct > 15:
                recommendations.append("Implement corrective actions for delayed milestones")
            if active_proj > 5:
                recommendations.append("Monitor resource allocation across high project count")
            if not recommendations:
                recommendations.append("Continue current tracking and monitoring")
            
            # --- Credit Deduction ---
            if user_id:
                CreditService.deduct_credits(user_id, None, "Executive Summary Generation", 5.0, "TASK")

            return json.dumps({
                "status": "success",
                "data": {
                    "period_days": time_period_days,
                    "portfolio_health": health,
                    "metrics": {
                        "total_projects": total_proj,
                        "active_projects": active_proj,
                        "completed_projects": completed_proj,
                        "completion_percentage": round(completion_pct, 1),
                        "total_budget": total_budget,
                        "total_spent": total_spent,
                        "spend_percentage": round(spend_pct, 1),
                        "delayed_milestones": delayed_m,
                        "delay_percentage": round(delay_pct, 1)
                    },
                    "key_findings": findings,
                    "recent_activities": activities[:5],
                    "recommendations": recommendations
                },
                "message": f"Executive summary for last {time_period_days} days"
            })
    except Exception as e:
        logger.error("Executive summary generation failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def generate_project_status_report(project_id: int, user_id: Optional[int] = None) -> str:
    """
    Generate detailed status report for a specific project.
    
    Includes:
    - Project overview
    - Budget status
    - Timeline status
    - Milestone progress
    - Key metrics
    - Issues and risks
    
    Input:
        project_id: Project to report on
        
    Output:
        Comprehensive project status report
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            # Get project details
            cursor.execute("""
                SELECT 
                    p.project_id,
                    p.project_name,
                    p.current_status,
                    c.company_name,
                    c.contact_person,
                    sow.total_budget,
                    sow.start_date,
                    sow.end_date,
                    v.vendor_name
                FROM projects p
                LEFT JOIN clients c ON p.client_id = c.client_id
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN vendors v ON sow.vendor_id = v.vendor_id
                WHERE p.project_id = ?
            """, (project_id,))
            
            proj_data = cursor.fetchone()
            if not proj_data:
                return json.dumps({"status": "error", "message": "Project not found"})
            
            proj_id, proj_name, status, client, contact, budget, start_date, end_date, vendor = proj_data
            
            # Get milestone status
            cursor.execute("""
                SELECT 
                    milestone_name,
                    status,
                    planned_delivery_date,
                    actual_delivery_date,
                    payment_amount
                FROM milestones
                WHERE sow_id IN (SELECT sow_id FROM statements_of_work WHERE project_id = ?)
                ORDER BY milestone_id
            """, (project_id,))
            
            milestones = []
            total_spent = 0
            for row in cursor.fetchall():
                m_name, m_status, planned, actual, amount = row
                if m_status == 'Completed':
                    total_spent += amount or 0
                milestones.append({
                    "name": m_name,
                    "status": m_status,
                    "planned_date": planned,
                    "actual_date": actual,
                    "amount": amount
                })
            
            # Calculate metrics
            completed = sum(1 for m in milestones if m["status"] == "Completed")
            total_milestones = len(milestones)
            progress = (completed / total_milestones * 100) if total_milestones else 0
            
            # Budget analysis
            budget_remaining = budget - total_spent if budget else 0
            budget_pct = (total_spent / budget * 100) if budget else 0
            
            # Timeline analysis
            past_deadline = False
            if end_date:
                end = datetime.fromisoformat(end_date)
                past_deadline = datetime.now() > end
            
            # Issues
            issues = []
            if budget_pct > 90:
                issues.append(f"BUDGET: Project at {budget_pct:.1f}% spend")
            if past_deadline:
                issues.append("TIMELINE: Project past scheduled end date")
            delayed_count = sum(1 for m in milestones if m["status"] == "Delayed")
            if delayed_count > 0:
                issues.append(f"MILESTONES: {delayed_count} milestone(s) delayed")
            if not issues:
                issues.append("No critical issues identified")
            
            # --- Credit Deduction ---
            if user_id:
                CreditService.deduct_credits(user_id, project_id, f"Project Status Report: {proj_name}", 5.0, "TASK")

            return json.dumps({
                "status": "success",
                "data": {
                    "project": {
                        "name": proj_name,
                        "status": status,
                        "client": client,
                        "contact": contact,
                        "vendor": vendor
                    },
                    "budget": {
                        "total": budget,
                        "spent": total_spent,
                        "remaining": budget_remaining,
                        "percentage_spent": round(budget_pct, 1)
                    },
                    "timeline": {
                        "start_date": start_date,
                        "end_date": end_date,
                        "past_deadline": past_deadline
                    },
                    "progress": {
                        "completed_milestones": completed,
                        "total_milestones": total_milestones,
                        "completion_percentage": round(progress, 1),
                        "milestones": milestones
                    },
                    "issues": issues
                },
                "message": f"Status report for {proj_name}"
            })
    except Exception as e:
        logger.error("Project status report failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def generate_portfolio_report() -> str:
    """
    Generate comprehensive portfolio overview report.
    
    Shows:
    - All projects with key metrics
    - Portfolio summary
    - Comparison across projects
    - Portfolio health indicators
    
    Output:
        Portfolio report with all project metrics
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    p.project_id,
                    p.project_name,
                    p.current_status,
                    c.company_name,
                    sow.total_budget,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN 1 ELSE 0 END) as completed_milestones,
                    SUM(CASE WHEN m.status = 'Delayed' THEN 1 ELSE 0 END) as delayed_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent
                FROM projects p
                LEFT JOIN clients c ON p.client_id = c.client_id
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                GROUP BY p.project_id
                ORDER BY p.project_name
            """)
            
            rows = cursor.fetchall()
            
            projects = []
            total_budget = 0
            total_spent = 0
            
            for row in rows:
                proj_id, proj_name, status, client, budget, total_m, completed_m, delayed_m, spent = row
                budget = budget or 0
                spent = spent or 0
                
                total_budget += budget
                total_spent += spent
                
                progress = (completed_m / total_m * 100) if total_m else 0
                budget_pct = (spent / budget * 100) if budget else 0
                
                projects.append({
                    "project_id": proj_id,
                    "name": proj_name,
                    "status": status,
                    "client": client,
                    "budget": budget,
                    "spent": spent,
                    "budget_percentage": round(budget_pct, 1),
                    "progress_percentage": round(progress, 1),
                    "total_milestones": total_m,
                    "completed": completed_m,
                    "delayed": delayed_m
                })
            
            # Portfolio summary
            overall_progress = (total_spent / total_budget * 100) if total_budget else 0
            
            return json.dumps({
                "status": "success",
                "data": {
                    "portfolio_summary": {
                        "total_projects": len(projects),
                        "total_budget": total_budget,
                        "total_spent": total_spent,
                        "overall_progress_percentage": round(overall_progress, 1)
                    },
                    "projects": projects,
                    "generated_at": datetime.now().isoformat()
                },
                "message": f"Portfolio report for {len(projects)} projects"
            })
    except Exception as e:
        logger.error("Portfolio report failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def generate_milestone_report(project_id: Optional[int] = None) -> str:
    """
    Generate detailed milestone tracking report.
    
    Shows:
    - All milestones with status
    - Completion dates vs planned dates
    - Payments and budget allocation
    - Timeline variance
    
    Input:
        project_id: Specific project, or all if None
        
    Output:
        Milestone report with detailed tracking
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            if project_id:
                cursor.execute("""
                    SELECT 
                        m.milestone_id,
                        m.milestone_name,
                        p.project_name,
                        m.status,
                        m.planned_delivery_date,
                        m.actual_delivery_date,
                        m.payment_amount
                    FROM milestones m
                    JOIN statements_of_work sow ON m.sow_id = sow.sow_id
                    JOIN projects p ON sow.project_id = p.project_id
                    WHERE p.project_id = ?
                    ORDER BY m.milestone_id
                """, (project_id,))
            else:
                cursor.execute("""
                    SELECT 
                        m.milestone_id,
                        m.milestone_name,
                        p.project_name,
                        m.status,
                        m.planned_delivery_date,
                        m.actual_delivery_date,
                        m.payment_amount
                    FROM milestones m
                    JOIN statements_of_work sow ON m.sow_id = sow.sow_id
                    JOIN projects p ON sow.project_id = p.project_id
                    ORDER BY p.project_name, m.milestone_id
                """)
            
            milestones = []
            on_time = 0
            late = 0
            
            for row in cursor.fetchall():
                m_id, m_name, p_name, status, planned, actual, amount = row
                
                days_variance = 0
                if actual and planned:
                    planned_dt = datetime.fromisoformat(planned)
                    actual_dt = datetime.fromisoformat(actual)
                    days_variance = (actual_dt - planned_dt).days
                
                if days_variance <= 0:
                    on_time += 1
                else:
                    late += 1
                
                milestones.append({
                    "milestone": m_name,
                    "project": p_name,
                    "status": status,
                    "planned_date": planned,
                    "actual_date": actual,
                    "days_variance": days_variance,
                    "payment_amount": amount,
                    "on_time": days_variance <= 0
                })
            
            on_time_pct = (on_time / len(milestones) * 100) if milestones else 0
            
            return json.dumps({
                "status": "success",
                "data": {
                    "total_milestones": len(milestones),
                    "on_time_count": on_time,
                    "late_count": late,
                    "on_time_percentage": round(on_time_pct, 1),
                    "milestones": milestones
                },
                "message": f"Milestone report for {len(milestones)} milestones"
            })
    except Exception as e:
        logger.error("Milestone report failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def export_report_data(report_type: str, format: str = "json") -> str:
    """
    Export report data in various formats.
    
    Supports formats: json, csv, markdown, html
    
    Input:
        report_type: 'portfolio', 'projects', 'milestones', 'budget', 'risk'
        format: 'json', 'csv', 'markdown', 'html'
        
    Output:
        Report data in requested format (as JSON with format indicator)
    """
    try:
        # For now, return JSON - frontend will handle conversion
        if report_type == "portfolio":
            cursor = get_db_connection(read_only=True).cursor()
            cursor.execute("""
                SELECT 
                    p.project_name,
                    p.current_status,
                    sow.total_budget,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent
                FROM projects p
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                GROUP BY p.project_id
            """)
            
            rows = cursor.fetchall()
            data = [{"project": r[0], "status": r[1], "budget": r[2], "spent": r[3]} for r in rows]
            
            return json.dumps({
                "status": "success",
                "data": data,
                "format": format,
                "export_type": report_type,
                "message": f"Exported {report_type} report in {format} format"
            })
        
        return json.dumps({
            "status": "error",
            "message": f"Report type '{report_type}' not yet implemented"
        })
    except Exception as e:
        logger.error("Report export failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})
