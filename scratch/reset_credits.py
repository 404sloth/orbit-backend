import sqlite3
import os
import sys

# Add the 'app' directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings

def reset_and_seed_credits():
    db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Drop existing tables
        tables = ['user_credits', 'credit_transactions', 'vendor_bills', 'yearly_closings']
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        
        print("✓ Dropped existing credit tables.")
        
        # 2. Re-create tables
        from db.credits import CREDIT_DDL
        cursor.executescript(CREDIT_DDL)
        print("✓ Re-created credit tables.")
        
        # 3. Get user 5 (Yash)
        cursor.execute("SELECT user_id, username FROM users WHERE user_id = 5")
        user = cursor.fetchone()
        if not user:
            cursor.execute("SELECT user_id, username FROM users LIMIT 1")
            user = cursor.fetchone()
        
        if not user:
            print("❌ No users found to seed.")
            return

        u_id, username = user
        print(f"🌱 Seeding data for {username} (ID: {u_id})")
        
        # 4. Seed User Credits
        # Initial CF: 3000.
        # Current Allocation: 5000.
        # Total Pool: 8000.
        # Used: 2500.
        # Remaining: 5500 (500 CF + 5000 Current).
        cursor.execute("""
            INSERT INTO user_credits (
                user_id, yearly_allocation, used_credits, remaining_credits, carry_forward_credits, financial_year
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (u_id, 5000.0, 2500.0, 5500.0, 500.0, '2024-2025'))

        # 5. Get projects
        cursor.execute("SELECT project_id FROM projects WHERE user_id = ? LIMIT 3", (u_id,))
        project_ids = [r[0] for r in cursor.fetchall()]
        
        if not project_ids:
            cursor.execute("INSERT INTO projects (project_name, user_id, current_status) VALUES (?, ?, ?)", 
                           ("Seeded Pool Project", u_id, "In Progress"))
            project_ids = [cursor.lastrowid]

        # 6. Seed Transactions
        transactions = [
            (u_id, None, "Annual Rollover", -3000.0, "CARRY_FORWARD", "Credits carried forward from FY 2023-24 Pool."),
            (u_id, project_ids[0], "API Integration Module", 800.0, "TASK", "Used 800.0 from Rollover, 0.0 from Current Year."),
            (u_id, project_ids[1] if len(project_ids) > 1 else project_ids[0], "Frontend Optimization", 700.0, "TASK", "Used 700.0 from Rollover, 0.0 from Current Year."),
            (u_id, project_ids[0], "Cloud Infrastructure Setup", 1000.0, "TASK", "Used 1000.0 from Rollover, 0.0 from Current Year.")
        ]
        
        for tx in transactions:
            cursor.execute("""
                INSERT INTO credit_transactions (user_id, project_id, task_name, credits_used, source_type, details)
                VALUES (?, ?, ?, ?, ?, ?)
            """, tx)

        # 7. Seed Vendor Bill
        cursor.execute("SELECT vendor_id FROM vendors LIMIT 1")
        v_row = cursor.fetchone()
        v_id = v_row[0] if v_row else 1
        
        cursor.execute("""
            INSERT INTO vendor_bills (user_id, vendor_id, project_id, total_amount, credits_applied, payable_amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (u_id, v_id, project_ids[0], 1200.0, 1200.0, 0.0, 'SETTLED'))

        conn.commit()
        print("✅ Database reset and seeded successfully.")
        
    except Exception as e:
        print(f"❌ Error during reset: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    reset_and_seed_credits()
