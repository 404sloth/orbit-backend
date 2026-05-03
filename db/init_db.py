"""
Database Initialization Script for Orbit.
Creates all tables in orbits.db with proper foreign keys and seeds rich, realistic sample data.
Run: python -m db.init_db   (from the /app directory)
"""
import sqlite3
import os
import sys

# Add the 'app' directory to sys.path so we can import 'core'
# This allows running: python3 init_db.py from the app/db directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings


DDL = """
PRAGMA foreign_keys = ON;

-- ===================== CORE ENTITIES =====================

CREATE TABLE IF NOT EXISTS clients (
    client_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    company_name    TEXT NOT NULL,
    contact_person  TEXT,
    industry        TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor_name     TEXT NOT NULL,
    tech_expertise  TEXT,
    rating          REAL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS projects (
    project_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id       INTEGER NOT NULL,
    user_id         INTEGER,
    project_name    TEXT NOT NULL,
    current_status  TEXT NOT NULL DEFAULT 'Discovery'
                    CHECK(current_status IN ('Discovery','RFP','Bidding','Active','Completed')),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(client_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ===================== RFP / BIDDING =====================

CREATE TABLE IF NOT EXISTS rfp_documents (
    rfp_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL,
    issue_date          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deadline            TIMESTAMP,
    budget_range_max    REAL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS vendor_bids (
    bid_id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    rfp_id                      INTEGER NOT NULL,
    vendor_id                   INTEGER NOT NULL,
    proposed_budget             REAL,
    estimated_timeline_weeks    INTEGER,
    bid_status                  TEXT DEFAULT 'Pending'
                                CHECK(bid_status IN ('Pending','Shortlisted','Rejected','Won')),
    technical_proposal_summary  TEXT,
    compliance_met              INTEGER DEFAULT 0,
    FOREIGN KEY (rfp_id)    REFERENCES rfp_documents(rfp_id),
    FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id)
);

-- ===================== DELIVERY =====================

CREATE TABLE IF NOT EXISTS statements_of_work (
    sow_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL,
    vendor_id       INTEGER NOT NULL,
    total_budget    REAL,
    start_date      DATE,
    end_date        DATE,
    signed_date     DATE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (vendor_id)  REFERENCES vendors(vendor_id)
);

CREATE TABLE IF NOT EXISTS milestones (
    milestone_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sow_id                  INTEGER NOT NULL,
    milestone_name          TEXT NOT NULL,
    description             TEXT,
    planned_delivery_date   DATE,
    actual_delivery_date    DATE,
    status                  TEXT DEFAULT 'Pending'
                            CHECK(status IN ('Pending','In-Progress','Completed','Delayed')),
    payment_amount          REAL,
    FOREIGN KEY (sow_id) REFERENCES statements_of_work(sow_id)
);

-- ===================== KNOWLEDGE =====================

CREATE TABLE IF NOT EXISTS meeting_transcripts (
    transcript_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER NOT NULL,
    meeting_date        TIMESTAMP,
    raw_text            TEXT,
    cleaned_summary     TEXT,
    processing_status   TEXT DEFAULT 'PENDING' CHECK(processing_status IN ('PENDING','DONE')),
    meeting_type        TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS project_requirements (
    requirement_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL,
    category        TEXT CHECK(category IN ('Budget','Tech-Stack','Privacy','Compliance')),
    description     TEXT,
    is_mandatory    INTEGER DEFAULT 1,
    priority        TEXT DEFAULT 'Medium' CHECK(priority IN ('High','Medium','Low')),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

-- ===================== MONITORING =====================

CREATE TABLE IF NOT EXISTS external_api_monitors (
    monitor_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL,
    site_url        TEXT,
    uptime_status   TEXT DEFAULT 'UP',
    last_checked    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE IF NOT EXISTS users (
    user_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username            TEXT UNIQUE NOT NULL,
    email               TEXT UNIQUE,
    hashed_password     TEXT NOT NULL,
    role                TEXT DEFAULT 'USER' CHECK(role IN ('ADMIN', 'USER', 'ANALYST')),
    is_active           INTEGER DEFAULT 1,
    is_verified         INTEGER DEFAULT 0,
    failed_attempts     INTEGER DEFAULT 0,
    locked_until        TIMESTAMP,
    last_login          TIMESTAMP,
    last_failed_login   TIMESTAMP,
    password_changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===================== CHAT AUDIT =====================

CREATE TABLE IF NOT EXISTS chat_history (
    chat_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id          INTEGER,
    user_id             INTEGER,
    message_content     TEXT,
    ai_response         TEXT,
    intent_identified   TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id  TEXT PRIMARY KEY,
    user_id    INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id  TEXT NOT NULL,
    role       TEXT NOT NULL CHECK(role IN ('user','assistant')),
    content    TEXT NOT NULL,
    metadata   TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id) ON DELETE CASCADE
);

-- ===================== SECURITY AUDIT =====================

CREATE TABLE IF NOT EXISTS security_events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    username        TEXT,
    ip_address      TEXT,
    user_agent      TEXT,
    details         TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permissions (
    permission_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_name TEXT UNIQUE NOT NULL,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS user_permissions (
    user_id       INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, permission_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(permission_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS access_gaps (
    gap_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    project_id      INTEGER NOT NULL,
    permission_id   INTEGER NOT NULL,
    reason          TEXT,
    severity        TEXT CHECK(severity IN ('high', 'medium', 'low')) DEFAULT 'medium',
    status          TEXT CHECK(status IN ('flagged', 'resolved', 'ignored')) DEFAULT 'flagged',
    last_active     TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (permission_id) REFERENCES permissions(permission_id)
);

-- ===================== DASHBOARD CACHE =====================

CREATE TABLE IF NOT EXISTS dashboard_metrics (
    metric_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_key  TEXT UNIQUE NOT NULL,
    status      TEXT,
    reason      TEXT,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS milestone_tasks (
    task_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id      INTEGER NOT NULL,
    task_description  TEXT NOT NULL,
    is_completed      INTEGER DEFAULT 0,
    FOREIGN KEY (milestone_id) REFERENCES milestones(milestone_id) ON DELETE CASCADE
);
"""
SEED_DATA = """
-- ===== USERS =====
INSERT OR REPLACE INTO users (user_id, username, email, hashed_password, role, is_active, is_verified)
VALUES
    (1, 'admin', 'admin@h-copilot.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'ADMIN', 1, 1),
    (2, 'sarah_whitman', 'sarah.w@greenfield.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'USER', 1, 1),
    (3, 'marcus_chen', 'm.chen@cloudforge.io', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'ANALYST', 1, 1),
    (4, 'elena_rodriguez', 'elena.r@wellspring.health', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'USER', 1, 1),
    (5, 'Anil', 'anil@h-copilot.com', '$argon2id$v=19$m=65536,t=3,p=4$2hsjBEAIIQTgHINQKmVM6Q$XiEDLBIGQW/wm/gKZ6CWh15CTosz/BR6XbX0P17wo+8', 'ADMIN', 1, 1),
    (6, 'Kashish', 'kashish@h-copilot.com', '$argon2id$v=19$m=65536,t=3,p=4$EYKQ8h6jVCql9J7zfi9FSA$8mV60hYEhDhqYhR9RyqfqQbpU0Ipd/SKz8833ZAnZ8o', 'ADMIN', 1, 1),
    (7, 'Purva', 'purva@h-copilot.com', '$argon2id$v=19$m=65536,t=3,p=4$E4JQyhlDKCXkvFeqdQ4BIA$sy9zxAs1XX8ZLCyf6efstcmCoXO7HeLv5Kqw7E6uiBk', 'USER', 1, 1),
    (8, 'Ruchi', 'ruchi@h-copilot.com', '$argon2id$v=19$m=65536,t=3,p=4$n3PuXSsFgHBujVGKkXLOOQ$pxcHATu85XAX1k0tgGvbkv8QWC98xY28+u9k2lUsVTY', 'USER', 1, 1),
    (9, 'Yash', 'yash@h-copilot.com', '$argon2id$v=19$m=65536,t=3,p=4$2hsjBEAIIQTgHINQKmVM6Q$XiEDLBIGQW/wm/gKZ6CWh15CTosz/BR6XbX0P17wo+8', 'USER', 1, 1);

-- ===== CLIENTS =====
INSERT OR REPLACE INTO clients (client_id, user_id, company_name, contact_person, industry)
VALUES
    (1, 1, 'Aegis Dynamics',        'Michael Chen',       'Aerospace & Defense'),
    (2, 4, 'Wellspring Health',     'Dr. Lisa Abernathy', 'Healthcare'),
    (3, 1, 'NovaLogic Systems',     'Arjun Mehta',        'Enterprise SaaS'),
    (4, 2, 'Greenfield Retail',     'Sarah Whitman',      'Retail & E-Commerce'),
    (5, 5, 'SkyNet Logistics',      'Anil Kumar',         'Supply Chain'),
    (6, 6, 'Vogue Fashion',         'Kashish Singh',      'Apparel'),
    (7, 9, 'Y-Tech Solutions',      'Yash Vardhan',       'Tech Consulting');

-- ===== VENDORS =====
INSERT OR REPLACE INTO vendors (vendor_id, vendor_name, tech_expertise, rating)
VALUES
    (1, 'CloudForge Solutions',  'AWS, Azure, Kubernetes, Terraform, CI/CD pipelines',                    4.6),
    (2, 'DataPulse AI',          'ML Engineering, MLOps, PyTorch, TensorFlow, Spark, Databricks',         4.9),
    (3, 'Sentinel CyberWorks',   'Zero-Trust Architecture, SOC2, ISO27001, Penetration Testing, IAM',      4.3),
    (4, 'PixelByte Studios',     'React, Next.js, Node.js, GraphQL, Full-Stack Web, Accessibility',        4.1),
    (5, 'Nebula Analytics',      'Data Warehousing, Snowflake, dbt, PowerBI, ETL/ELT, Data Governance',    4.7);

-- ===== PROJECTS =====
INSERT OR REPLACE INTO projects (project_id, client_id, user_id, project_name, current_status)
VALUES
    (1, 1, 1, 'Phoenix ERP Modernization',           'Active'),
    (2, 2, 4, 'Patient 360 Portal',                  'RFP'),
    (3, 3, 1, 'AI‑Native Analytics Platform',         'Bidding'),
    (4, 1, 1, 'Supply Chain Security Overhaul',       'Completed'),
    (5, 4, 2, 'Omnichannel Dashboard Unification',    'Discovery'),
    (6, 5, 5, 'Global Supply Chain Audit',           'Active'),
    (7, 6, 6, 'E-Commerce Cloud Migration',          'RFP'),
    (8, 3, 5, 'Strategic Growth Strategy 2026',      'Active'),
    (9, 7, 9, 'Y-Tech Infrastructure Scaling',       'Active'),
    (10, 5, 5, 'Warehouse Automation PoC',           'Discovery'),
    (11, 6, 6, 'AI Personal Shopper Integration',    'Bidding'),
    (12, 4, 7, 'Purva - Retail Expansion Phase 2',    'Active'),
    (13, 1, 5, 'Anil - Advanced Logistics AI',       'Bidding'),
    (14, 7, 9, 'Yash - Cloud Security Hardening',    'Active'),
    (15, 6, 6, 'Kashish - Global Supply Node 2',     'Completed');

-- ===== RFP DOCUMENTS =====
INSERT OR REPLACE INTO rfp_documents (rfp_id, project_id, issue_date, deadline, budget_range_max)
VALUES
    (1, 1, '2025-01-15', '2025-02-28', 750000),
    (2, 2, '2025-03-10', '2025-04-15', 400000),
    (3, 3, '2025-06-05', '2025-07-20', 1200000),
    (4, 7, '2025-09-01', '2025-10-15', 550000);

-- ===== VENDOR BIDS =====
INSERT OR REPLACE INTO vendor_bids (bid_id, rfp_id, vendor_id, proposed_budget, estimated_timeline_weeks, bid_status, technical_proposal_summary, compliance_met)
VALUES
    (1, 1, 1, 695000, 28, 'Won',        'Comprehensive lift-and-shift with containerisation, phased cutover, and integrated monitoring dashboards.', 1),
    (2, 1, 3, 720000, 32, 'Rejected',   'Hybrid approach with on-premise gateway and cloud analytics layer.', 1),
    (3, 2, 4, 375000, 20, 'Shortlisted', 'Modern React/Next.js portal with FHIR API integration and WCAG 2.1 AA compliance.', 1),
    (4, 2, 2, 390000, 22, 'Pending',     'AI‑driven patient triage with ML models for readmission risk.', 0),
    (5, 3, 2, 980000, 36, 'Shortlisted', 'End‑to‑end ML platform on Kubernetes with feature store and model registry.', 1),
    (6, 7, 1, 510000, 24, 'Won',         'Full migration to AWS using Lambda and RDS, with automated CI/CD pipelines.', 1);

-- ===== STATEMENTS OF WORK =====
INSERT OR REPLACE INTO statements_of_work (sow_id, project_id, vendor_id, total_budget, start_date, end_date, signed_date)
VALUES
    (1, 1, 1, 695000, '2025-04-01', '2025-10-15', '2025-03-18'),
    (2, 4, 3, 185000, '2024-07-15', '2024-12-31', '2024-07-01'),
    (3, 2, 4, 375000, '2025-05-01', '2025-09-30', '2025-04-10'),
    (4, 3, 2, 910000, '2025-08-01', '2026-03-31', '2025-07-15'),
    (5, 6, 3, 250000, '2025-08-15', '2025-12-31', '2025-08-01');

-- ===== MILESTONES =====
INSERT OR REPLACE INTO milestones (milestone_id, sow_id, milestone_name, description, planned_delivery_date, actual_delivery_date, status, payment_amount)
VALUES
    (1, 1, 'M1 – Current State Audit',              'Discovery of legacy ERP modules (finance, HR, supply chain).',          '2025-05-15', '2025-05-19', 'Completed',    80000),
    (2, 1, 'M2 – Core Data Migration',               'Migrate 14 critical data tables to cloud PostgreSQL.', '2025-07-01', NULL,         'In-Progress', 175000),
    (3, 1, 'M3 – Integration & Performance Testing', 'End‑to‑end integration testing and load testing.',                        '2025-08-15', NULL,         'Pending',     150000),
    (4, 6, 'M1 – Network Vulnerability Scan',        'Security audit of global warehouse network endpoints.',                '2025-09-10', '2025-09-12', 'Completed',    50000),
    (5, 6, 'M2 – Access Control Remediation',        'Fixing identified IAM gaps and implementing MFA.',                     '2025-11-01', NULL,         'In-Progress', 100000);

-- ===== PROJECT REQUIREMENTS =====
INSERT OR REPLACE INTO project_requirements (requirement_id, project_id, category, description, is_mandatory, priority)
VALUES
    (1,  1, 'Tech-Stack',  'Target architecture must be containerized on Kubernetes.', 1, 'High'),
    (2,  1, 'Budget',      'Total implementation cost must not exceed $750,000.', 1, 'High'),
    (3,  6, 'Compliance',  'Must comply with NIST 800-53 security standards.', 1, 'High'),
    (4,  6, 'Privacy',     'All supplier PII must be encrypted using AES-256.', 1, 'High');

-- ===== MEETING TRANSCRIPTS =====
INSERT OR REPLACE INTO meeting_transcripts (transcript_id, project_id, meeting_date, raw_text, cleaned_summary, processing_status, meeting_type)
VALUES
    (1, 1, '2025-04-10 10:00:00',
     'Anil (SkyNet): Thanks for joining. We need to finalize the ERP cutover.
Kashish (Vogue): I''m concerned about the integration with our fashion portal.
Sarah (CloudForge): We have a plan for the blue-green deployment. IP lists will be ready by Thursday.',
     'Cutover planning for ERP. Blue-green deployment confirmed.',
     'DONE', 'Kickoff'),
    (2, 6, '2025-09-15 14:00:00',
     'Anil (SkyNet): The network scan found 42 critical vulnerabilities. We need remediation ASAP.
Purva (Sentinel): We''ll start patching tomorrow. Most are related to outdated router firmware.
Ruchi (Analyst): I''ll monitor the impact on delivery latency during the patch window.',
     'Security audit findings: 42 vulnerabilities found. Remediation starting tomorrow.',
     'DONE', 'Security Audit Sync'),
    (3, 8, '2025-10-01 09:00:00',
     'Anil (SkyNet): We need to finalize the 2026 growth strategy.
Ruchi (Analyst): The data suggests a 15% increase in demand for autonomous delivery in the APAC region.
Purva (Sentinel): We must ensure the security of the drone fleet APIs.',
     'Strategy sync: APAC growth focus and drone API security.',
     'PENDING', 'Strategy Session');

-- ===== EXTERNAL API MONITORS =====
INSERT OR REPLACE INTO external_api_monitors (monitor_id, project_id, site_url, uptime_status, last_checked)
VALUES
    (1, 1, 'https://erp-staging.aegisdynamics.com/health',            'UP',   '2025-04-25T10:00:00'),
    (2, 6, 'https://audit.skynet-logistics.com/v1/status',            'UP',   '2025-09-20T11:00:00');

-- ===== CHAT HISTORY =====
INSERT OR REPLACE INTO chat_history (chat_id, project_id, user_id, message_content, ai_response, intent_identified, created_at)
VALUES
    (1, 1, 1, 'Status of Phoenix?', 'Active. Milestone M2 In-Progress.', 'query', '2025-05-21T08:30:00'),
    (2, 6, 5, 'Security audit progress?', 'M1 completed. 42 vulnerabilities identified.', 'query', '2025-09-16T10:00:00');

-- ===== SECURITY EVENTS =====
INSERT OR REPLACE INTO security_events (event_id, event_type, username, ip_address, user_agent, details, created_at)
VALUES
    (1, 'LOGIN_SUCCESS', 'Anil', '192.168.1.15', 'Chrome/120.0', 'Successful login.', '2025-09-15T08:00:00'),
    (2, 'ACCESS_DENIED', 'Kashish', '10.0.0.5', 'Firefox/118', 'Unauthorized attempt to access audit logs.', '2025-09-15T12:00:00');

-- ===== PERMISSIONS =====
INSERT OR REPLACE INTO permissions (permission_id, permission_name, description)
VALUES
    (1, 'Financial Ledger Write', 'Modify accounting ledgers.'),
    (2, 'Security Audit Read', 'View security audit findings.'),
    (3, 'Drone Fleet Control', 'Access to drone management system.');

-- ===== ACCESS GAPS =====
INSERT OR REPLACE INTO access_gaps (user_id, project_id, permission_id, reason, severity, status, last_active)
VALUES
    (6, 6, 2, 'User has read access to audit logs but is not in the security team.', 'medium', 'flagged', '2025-09-15T12:00:00');

-- ===== MILESTONE TASKS =====
INSERT OR REPLACE INTO milestone_tasks (milestone_id, task_description, is_completed)
VALUES
    (4, 'Scan warehouse network endpoints', 1),
    (4, 'Identify firmware versions', 1),
    (5, 'Update router firmware', 0),
    (5, 'Implement MFA for warehouse staff', 0),
    (9, 'Create high-fidelity Figma mockups', 1),
    (9, 'Conduct initial screen reader audit', 0),
    (10, 'Configure Kueue GPU scheduling', 0),
    (10, 'Setup model registry', 0);
"""


def init_database():
    """Create all tables and seed sample data into orbits.db."""
    db_path = settings.db_path
    print(f"Initializing database at: {os.path.abspath(db_path)}")

    conn = sqlite3.connect(db_path)
    conn.executescript(DDL)
    print("✓ All tables created.")

    cursor = conn.cursor()
    print("Applying/Updating sample data...")
    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.executescript(SEED_DATA)
    conn.execute("PRAGMA foreign_keys = ON;")
    print("✓ Sample data applied.")

    # Verify
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"✓ Tables present: {tables}")

    conn.close()
    print("Database initialization complete.")


if __name__ == "__main__":
    init_database()