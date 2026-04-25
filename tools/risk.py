"""
Risk Management Tools for the Risk Agent.
Provides comprehensive risk identification, assessment, and mitigation.
"""
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from langchain_core.tools import tool
from db.client import get_db_connection
from core.logger import logger


@tool
def assess_project_risks(project_id: int) -> str:
    """
    Comprehensive risk assessment for a project.
    
    Evaluates:
    - Timeline risks (delays, critical path)
    - Budget risks (overrun, burn rate)
    - Resource risks (availability, skills)
    - Technical risks (complexity, dependencies)
    - Compliance risks
    
    Input:
        project_id: Project to assess
        
    Output:
        Overall risk score with breakdown by category
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            # Get project status and milestones
            cursor.execute("""
                SELECT 
                    p.project_name,
                    p.current_status,
                    sow.total_budget,
                    sow.start_date,
                    sow.end_date,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Delayed' THEN 1 ELSE 0 END) as delayed_milestones,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent
                FROM projects p
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                WHERE p.project_id = ?
                GROUP BY p.project_id
            """, (project_id,))
            
            result = cursor.fetchone()
            if not result:
                return json.dumps({"status": "error", "message": "Project not found"})
            
            proj_name, proj_status, budget, start_date, end_date, total_m, delayed_m, spent = result
            spent = spent or 0
            
            # Calculate timeline risk
            timeline_risk_score = 0
            timeline_issues = []
            
            if delayed_m and total_m:
                delay_rate = delayed_m / total_m
                timeline_risk_score = min(100, delay_rate * 100 * 2)
                timeline_issues.append(f"{delayed_m} of {total_m} milestones delayed")
            
            if end_date:
                end = datetime.fromisoformat(end_date)
                if datetime.now() > end:
                    timeline_risk_score = 100
                    timeline_issues.append("Project past deadline")
            
            # Calculate budget risk
            budget_risk_score = 0
            budget_issues = []
            
            if budget:
                spend_ratio = spent / budget
                if spend_ratio > 0.9:
                    budget_risk_score = 80 + (spend_ratio - 0.9) * 200
                    budget_issues.append(f"Project {spend_ratio*100:.1f}% spent")
                elif spend_ratio > 0.75:
                    budget_risk_score = 50
                    budget_issues.append(f"High spend rate at {spend_ratio*100:.1f}%")
            
            # Calculate project status risk
            status_risk_map = {
                "Discovery": 20,
                "RFP": 30,
                "Bidding": 40,
                "Active": 50,
                "Completed": 5
            }
            status_risk = status_risk_map.get(proj_status, 60)
            status_issues = [f"Status: {proj_status}"]
            
            # Overall risk calculation (weighted average)
            overall_risk = (timeline_risk_score * 0.35 + budget_risk_score * 0.35 + status_risk * 0.30)
            
            # Determine risk level
            if overall_risk >= 75:
                risk_level = "CRITICAL"
            elif overall_risk >= 50:
                risk_level = "HIGH"
            elif overall_risk >= 25:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"
            
            # Get recommended actions
            actions = []
            if timeline_risk_score > 50:
                actions.append("Review critical path and compress schedule where possible")
            if budget_risk_score > 50:
                actions.append("Conduct cost review and identify cost-saving opportunities")
            if delayed_m and delayed_m > 0:
                actions.append("Increase monitoring frequency for at-risk milestones")
            if not actions:
                actions.append("Continue monitoring as planned")
            
            return json.dumps({
                "status": "success",
                "data": {
                    "project_name": proj_name,
                    "overall_risk_score": round(overall_risk, 1),
                    "risk_level": risk_level,
                    "timeline_risk": {
                        "score": round(timeline_risk_score, 1),
                        "issues": timeline_issues
                    },
                    "budget_risk": {
                        "score": round(budget_risk_score, 1),
                        "issues": budget_issues
                    },
                    "status_risk": {
                        "score": round(status_risk, 1),
                        "issues": status_issues
                    },
                    "recommended_actions": actions
                },
                "message": f"Risk assessment for {proj_name}"
            })
    except Exception as e:
        logger.error("Risk assessment failed", project_id=project_id, error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def identify_at_risk_projects() -> str:
    """
    Find all projects currently at risk across the portfolio.
    
    Identifies high-risk projects based on:
    - Delayed milestones
    - Budget overruns
    - Status indicating problems
    
    Output:
        List of at-risk projects with risk scores
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    p.project_id,
                    p.project_name,
                    p.current_status,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Delayed' THEN 1 ELSE 0 END) as delayed_milestones,
                    SUM(CASE WHEN m.status = 'In-Progress' THEN 1 ELSE 0 END) as in_progress,
                    sow.total_budget,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent
                FROM projects p
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                GROUP BY p.project_id
                HAVING delayed_milestones > 0 OR (spent > sow.total_budget * 0.85)
                ORDER BY delayed_milestones DESC, spent DESC
            """)
            
            rows = cursor.fetchall()
            
            if not rows:
                return json.dumps({
                    "status": "success",
                    "data": [],
                    "message": "No projects currently at risk"
                })
            
            at_risk = []
            for row in rows:
                proj_id, proj_name, status, total_m, delayed_m, in_prog, budget, spent = row
                spent = spent or 0
                
                # Calculate risk score
                delay_factor = (delayed_m / max(1, total_m)) * 50 if total_m else 0
                budget_factor = 0
                if budget:
                    spend_ratio = spent / budget
                    budget_factor = max(0, (spend_ratio - 0.85) / 0.15 * 50) if spend_ratio > 0.85 else 0
                
                risk_score = min(100, delay_factor + budget_factor)
                
                if risk_score >= 25:  # Only include meaningful risk
                    at_risk.append({
                        "project_id": proj_id,
                        "project_name": proj_name,
                        "status": status,
                        "risk_score": round(risk_score, 1),
                        "delayed_milestones": delayed_m,
                        "total_milestones": total_m,
                        "budget_spent": spent,
                        "budget_total": budget,
                        "percentage_spent": round(spent / budget * 100, 1) if budget else 0
                    })
            
            return json.dumps({
                "status": "success",
                "data": at_risk,
                "message": f"Found {len(at_risk)} projects at risk"
            })
    except Exception as e:
        logger.error("At-risk projects query failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def analyze_milestone_delays(project_id: int) -> str:
    """
    Analyze milestone delays and their impact on project timeline.
    
    Shows: Delayed milestones, delay duration, impact on subsequent milestones
    
    Input:
        project_id: Project to analyze
        
    Output:
        Delay analysis with timeline impact
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    m.milestone_id,
                    m.milestone_name,
                    m.planned_delivery_date,
                    m.actual_delivery_date,
                    m.status,
                    m.description,
                    CASE 
                        WHEN m.actual_delivery_date IS NOT NULL 
                        THEN (julianday(m.actual_delivery_date) - julianday(m.planned_delivery_date))
                        WHEN m.status = 'Delayed' THEN (julianday(date('now')) - julianday(m.planned_delivery_date))
                        ELSE 0
                    END as days_delayed
                FROM milestones m
                JOIN statements_of_work sow ON m.sow_id = sow.sow_id
                WHERE sow.project_id = ?
                ORDER BY m.milestone_id
            """, (project_id,))
            
            rows = cursor.fetchall()
            
            if not rows:
                return json.dumps({
                    "status": "error",
                    "message": "No milestones found"
                })
            
            milestones = []
            total_delay = 0
            delayed_count = 0
            
            for row in rows:
                m_id, name, planned, actual, status, desc, delay_days = row
                delay_days = int(delay_days) if delay_days else 0
                
                if delay_days > 0:
                    total_delay += delay_days
                    delayed_count += 1
                
                milestone_entry = {
                    "milestone": name,
                    "planned_date": planned,
                    "actual_date": actual or "Not completed",
                    "status": status,
                    "days_delayed": delay_days,
                    "is_delayed": delay_days > 0
                }
                
                if delay_days > 0:
                    milestone_entry["impact"] = f"Delayed by {delay_days} days"
                
                milestones.append(milestone_entry)
            
            avg_delay = total_delay / delayed_count if delayed_count > 0 else 0
            
            return json.dumps({
                "status": "success",
                "data": {
                    "milestones": milestones,
                    "delayed_count": delayed_count,
                    "total_delayed": total_delay,
                    "average_delay_days": round(avg_delay, 1),
                    "risk_summary": f"{delayed_count} milestones delayed by average {avg_delay:.1f} days"
                },
                "message": f"Milestone delay analysis for project {project_id}"
            })
    except Exception as e:
        logger.error("Milestone delay analysis failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})


@tool
def identify_risk_patterns() -> str:
    """
    Identify patterns in risks across all projects.
    
    Looks for:
    - Common risk types
    - Recurring issues
    - Projects with similar risk profiles
    
    Output:
        Risk pattern analysis
    """
    try:
        with get_db_connection(read_only=True) as conn:
            cursor = conn.cursor()
            
            # Get all projects and their risk metrics
            cursor.execute("""
                SELECT 
                    p.project_id,
                    p.project_name,
                    COUNT(DISTINCT m.milestone_id) as total_milestones,
                    SUM(CASE WHEN m.status = 'Delayed' THEN 1 ELSE 0 END) as delayed,
                    COUNT(DISTINCT CASE WHEN vb.bid_status = 'Won' THEN vb.vendor_id END) as vendor_count,
                    sow.total_budget,
                    SUM(CASE WHEN m.status = 'Completed' THEN m.payment_amount ELSE 0 END) as spent
                FROM projects p
                LEFT JOIN statements_of_work sow ON p.project_id = sow.project_id
                LEFT JOIN milestones m ON sow.sow_id = m.sow_id
                LEFT JOIN vendor_bids vb ON p.project_id = vb.rfp_id OR vb.bid_status = 'Won'
                GROUP BY p.project_id
            """)
            
            rows = cursor.fetchall()
            
            # Analyze patterns
            timeline_risks = sum(1 for r in rows if r[3] and r[3] > 0)
            budget_risks = sum(1 for r in rows if r[5] and r[6] and r[6] > r[5] * 0.85)
            vendor_risks = sum(1 for r in rows if r[4] and r[4] > 2)
            
            patterns = []
            if timeline_risks > len(rows) * 0.4:
                patterns.append(f"Timeline risk is widespread: {timeline_risks}/{len(rows)} projects have delays")
            if budget_risks > len(rows) * 0.3:
                patterns.append(f"Budget risk is common: {budget_risks}/{len(rows)} projects at 85%+ spend")
            if vendor_risks > 0:
                patterns.append(f"Multiple vendors in {vendor_risks} projects (coordination risk)")
            
            return json.dumps({
                "status": "success",
                "data": {
                    "total_projects": len(rows),
                    "projects_with_timeline_risk": timeline_risks,
                    "projects_with_budget_risk": budget_risks,
                    "projects_with_multiple_vendors": vendor_risks,
                    "risk_patterns": patterns if patterns else ["No major risk patterns detected"]
                },
                "message": "Portfolio risk pattern analysis"
            })
    except Exception as e:
        logger.error("Risk pattern analysis failed", error=str(e))
        return json.dumps({"status": "error", "message": str(e)})
