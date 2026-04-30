import sqlite3
import os
import sys

# Add the 'app' directory to sys.path so we can import 'core'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings

CREDIT_DDL = """
-- ===================== CREDIT MANAGEMENT =====================

CREATE TABLE IF NOT EXISTS user_credits (
    user_id                 INTEGER PRIMARY KEY,
    yearly_allocation       REAL DEFAULT 0.0,
    used_credits            REAL DEFAULT 0.0,
    remaining_credits       REAL DEFAULT 0.0,
    carry_forward_credits   REAL DEFAULT 0.0,
    financial_year          TEXT NOT NULL,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS credit_transactions (
    transaction_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    project_id      INTEGER,
    task_name       TEXT,
    credits_used    REAL NOT NULL,
    source_type     TEXT NOT NULL CHECK(source_type IN ('TASK', 'BILLING_ADJUSTMENT', 'ALLOCATION', 'CARRY_FORWARD', 'REFUND')),
    details         TEXT,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS vendor_bills (
    bill_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    vendor_id       INTEGER NOT NULL,
    project_id      INTEGER NOT NULL,
    total_amount    REAL NOT NULL,
    credits_applied REAL DEFAULT 0.0,
    payable_amount  REAL NOT NULL,
    status          TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'PARTIAL', 'SETTLED')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS yearly_closings (
    closing_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL,
    financial_year          TEXT NOT NULL,
    unused_credits          REAL NOT NULL,
    carried_forward_amount  REAL NOT NULL,
    closed_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
"""

def init_credits():
    db_path = settings.db_path
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(CREDIT_DDL)
        
        # Seed initial credits for existing users if not present
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        
        for (u_id,) in users:
            cursor.execute("SELECT COUNT(*) FROM user_credits WHERE user_id = ?", (u_id,))
            if cursor.fetchone()[0] == 0:
                # Default 5000 credits for everyone for testing
                cursor.execute("""
                    INSERT INTO user_credits (user_id, yearly_allocation, remaining_credits, financial_year)
                    VALUES (?, 5000.0, 5000.0, '2024-2025')
                """, (u_id,))
        
        conn.commit()
        print("✓ Credit Management tables initialized and seeded.")
    except Exception as e:
        print(f"Error initializing credits: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    init_credits()
