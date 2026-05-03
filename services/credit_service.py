from datetime import datetime
from typing import List, Dict, Any, Optional
from core.logger import logger
from db.client import get_db_connection

class CreditService:
    @staticmethod
    def get_summary(user_id: int, role: str = "USER") -> Dict[str, Any]:
        """Returns the credit summary for a user."""
        try:
            with get_db_connection() as conn:
                # 1. Get User Balance
                cursor = conn.execute("""
                    SELECT yearly_allocation, used_credits, remaining_credits, carry_forward_credits, financial_year
                    FROM user_credits WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                
                if not row:
                    return {
                        "total": 0, "used": 0, "remaining": 0, "carryForward": 0, 
                        "financialYear": "N/A", "projectUsage": [], "recentTransactions": []
                    }
                
                summary = {
                    "total": row[0],
                    "used": row[1],
                    "remaining": row[2],
                    "carryForward": row[3],
                    "financialYear": row[4]
                }
                
                # 2. Get Project Wise Usage (Role Aware)
                usage_query = """
                    SELECT p.project_name, SUM(ct.credits_used) as project_total, MAX(ct.timestamp) as last_used
                    FROM credit_transactions ct
                    JOIN projects p ON ct.project_id = p.project_id
                """
                usage_params = []
                if user_id is not None:
                    usage_query += " WHERE p.user_id = ?"
                    usage_params.append(user_id)
                
                usage_query += " GROUP BY ct.project_id"
                
                cursor = conn.execute(usage_query, usage_params)
                summary["projectUsage"] = [
                    {"name": r[0], "used": r[1], "lastUsed": r[2]} for r in cursor.fetchall()
                ]
                
                # 3. Get Recent Transactions (Role Aware)
                tx_query = """
                    SELECT ct.task_name, ct.credits_used, ct.timestamp, ct.source_type, ct.details
                    FROM credit_transactions ct
                    LEFT JOIN projects p ON ct.project_id = p.project_id
                """
                tx_params = []
                if user_id is not None:
                    tx_query += " WHERE ct.user_id = ? OR p.user_id = ?"
                    tx_params.extend([user_id, user_id])
                
                tx_query += " ORDER BY ct.timestamp DESC LIMIT 10"
                
                cursor = conn.execute(tx_query, tx_params)
                summary["recentTransactions"] = [
                    {"task": r[0], "amount": r[1], "date": r[2], "type": r[3], "details": r[4]} for r in cursor.fetchall()
                ]
                
                return summary
        except Exception as e:
            logger.error(f"Error fetching credit summary: {e}")
            return {}

    @staticmethod
    def deduct_credits(user_id: int, project_id: Optional[int], task_name: str, amount: float, source_type: str = "TASK") -> bool:
        """
        Deducts credits prioritizing Carried Forward credits (Rollover Pool) 
        before using the current year's allocation.
        """
        try:
            with get_db_connection(read_only=False) as conn:
                # 1. Get current balance components
                cursor = conn.execute("""
                    SELECT remaining_credits, carry_forward_credits 
                    FROM user_credits WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                if not row or row[0] < amount:
                    return False
                
                total_remaining = row[0]
                cf_credits = row[1]
                
                # 2. Calculate deductions
                cf_deduction = min(cf_credits, amount)
                main_deduction = amount - cf_deduction
                
                # 3. Update Pools
                conn.execute("""
                    UPDATE user_credits 
                    SET used_credits = used_credits + ?, 
                        remaining_credits = remaining_credits - ?,
                        carry_forward_credits = carry_forward_credits - ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (amount, amount, cf_deduction, user_id))
                
                # 4. Log Transaction with detail about which pool was used
                pool_info = f"Used {cf_deduction} from Rollover, {main_deduction} from Current Year."
                conn.execute("""
                    INSERT INTO credit_transactions (user_id, project_id, task_name, credits_used, source_type, details)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, project_id, task_name, amount, source_type, pool_info))
                
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error deducting credits: {e}")
            return False

    @staticmethod
    def adjust_vendor_bill(user_id: int, vendor_id: int, project_id: int, total_amount: float) -> Dict[str, Any]:
        """
        Adjusts a vendor bill prioritizing Rollover credits.
        """
        try:
            with get_db_connection(read_only=False) as conn:
                # 1. Get available pools
                cursor = conn.execute("""
                    SELECT remaining_credits, carry_forward_credits 
                    FROM user_credits WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                total_available = row[0] if row else 0
                cf_credits = row[1] if row else 0
                
                credits_applied = min(total_available, total_amount)
                payable_amount = total_amount - credits_applied
                
                # 2. Calculate deductions
                cf_deduction = min(cf_credits, credits_applied)
                main_deduction = credits_applied - cf_deduction
                
                # 3. Deduct if applied
                if credits_applied > 0:
                    conn.execute("""
                        UPDATE user_credits 
                        SET used_credits = used_credits + ?, 
                            remaining_credits = remaining_credits - ?,
                            carry_forward_credits = carry_forward_credits - ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (credits_applied, credits_applied, cf_deduction, user_id))
                    
                    # Log Transaction
                    pool_info = f"Bill adjustment: {cf_deduction} from Rollover, {main_deduction} from Current Year."
                    conn.execute("""
                        INSERT INTO credit_transactions (user_id, project_id, task_name, credits_used, source_type, details)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (user_id, project_id, "Vendor Bill Offset", credits_applied, "BILLING_ADJUSTMENT", pool_info))

                # 4. Save Bill
                status = "SETTLED" if payable_amount == 0 else ("PARTIAL" if credits_applied > 0 else "PENDING")
                cursor = conn.execute("""
                    INSERT INTO vendor_bills (user_id, vendor_id, project_id, total_amount, credits_applied, payable_amount, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, vendor_id, project_id, total_amount, credits_applied, payable_amount, status))
                bill_id = cursor.lastrowid
                
                conn.commit()
                return {
                    "bill_id": bill_id,
                    "total": total_amount,
                    "applied": credits_applied,
                    "payable": payable_amount,
                    "status": status,
                    "rollover_used": cf_deduction,
                    "current_year_used": main_deduction
                }
        except Exception as e:
            logger.error(f"Error adjusting vendor bill: {e}")
            return {}

    @staticmethod
    def close_financial_year(user_id: int, next_year_allocation: float = 5000.0) -> bool:
        """Closes the financial year and carries forward remaining credits."""
        try:
            with get_db_connection(read_only=False) as conn:
                # 1. Get current status
                cursor = conn.execute("""
                    SELECT financial_year, remaining_credits FROM user_credits WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                if not row: return False
                
                old_year = row[0]
                remaining = row[1]
                
                # 2. Record Closing
                conn.execute("""
                    INSERT INTO yearly_closings (user_id, financial_year, unused_credits, carried_forward_amount)
                    VALUES (?, ?, ?, ?)
                """, (user_id, old_year, remaining, remaining))
                
                # 3. Reset for New Year
                new_year_parts = old_year.split("-")
                new_year = f"{int(new_year_parts[0])+1}-{int(new_year_parts[1])+1}"
                
                conn.execute("""
                    UPDATE user_credits 
                    SET yearly_allocation = ?,
                        used_credits = 0,
                        remaining_credits = ? + ?,
                        carry_forward_credits = ?,
                        financial_year = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (next_year_allocation, next_year_allocation, remaining, remaining, new_year, user_id))
                
                # 4. Log Carry Forward
                conn.execute("""
                    INSERT INTO credit_transactions (user_id, task_name, credits_used, source_type, details)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, "Carry Forward", -remaining, "CARRY_FORWARD", f"From {old_year} to {new_year}"))

                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error closing financial year: {e}")
            return False
