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
INSERT OR IGNORE INTO users (user_id, username, email, hashed_password, role, is_active, is_verified)
VALUES
    (1, 'admin', 'admin@h-copilot.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'ADMIN', 1, 1),
    (2, 'sarah_whitman', 'sarah.w@greenfield.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'USER', 1, 1),
    (3, 'marcus_chen', 'm.chen@cloudforge.io', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'ANALYST', 1, 1),
    (4, 'elena_rodriguez', 'elena.r@wellspring.health', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj6fM9q7F6e', 'USER', 1, 1);

-- ===== CLIENTS =====
INSERT OR IGNORE INTO clients (client_id, user_id, company_name, contact_person, industry)
VALUES
    (1, 1, 'Aegis Dynamics',        'Michael Chen',       'Aerospace & Defense'),
    (2, 4, 'Wellspring Health',     'Dr. Lisa Abernathy', 'Healthcare'),
    (3, 1, 'NovaLogic Systems',     'Arjun Mehta',        'Enterprise SaaS'),
    (4, 2, 'Greenfield Retail',     'Sarah Whitman',      'Retail & E-Commerce');

-- ===== VENDORS =====
INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, tech_expertise, rating)
VALUES
    (1, 'CloudForge Solutions',  'AWS, Azure, Kubernetes, Terraform, CI/CD pipelines',                    4.6),
    (2, 'DataPulse AI',          'ML Engineering, MLOps, PyTorch, TensorFlow, Spark, Databricks',         4.9),
    (3, 'Sentinel CyberWorks',   'Zero-Trust Architecture, SOC2, ISO27001, Penetration Testing, IAM',      4.3),
    (4, 'PixelByte Studios',     'React, Next.js, Node.js, GraphQL, Full-Stack Web, Accessibility',        4.1),
    (5, 'Nebula Analytics',      'Data Warehousing, Snowflake, dbt, PowerBI, ETL/ELT, Data Governance',    4.7);

-- ===== PROJECTS =====
INSERT OR IGNORE INTO projects (project_id, client_id, user_id, project_name, current_status)
VALUES
    (1, 1, 1, 'Phoenix ERP Modernization',           'Active'),
    (2, 2, 4, 'Patient 360 Portal',                  'RFP'),
    (3, 3, 1, 'AI‑Native Analytics Platform',         'Bidding'),
    (4, 1, 1, 'Supply Chain Security Overhaul',       'Completed'),
    (5, 4, 2, 'Omnichannel Dashboard Unification',    'Discovery');

-- ===== RFP DOCUMENTS =====
INSERT OR IGNORE INTO rfp_documents (rfp_id, project_id, issue_date, deadline, budget_range_max)
VALUES
    (1, 1, '2025-01-15', '2025-02-28', 750000),
    (2, 2, '2025-03-10', '2025-04-15', 400000),
    (3, 3, '2025-06-05', '2025-07-20', 1200000);

-- ===== VENDOR BIDS =====
INSERT OR IGNORE INTO vendor_bids (bid_id, rfp_id, vendor_id, proposed_budget, estimated_timeline_weeks, bid_status, technical_proposal_summary, compliance_met)
VALUES
    (1, 1, 1, 695000, 28, 'Won',        'Comprehensive lift-and-shift with containerisation, phased cutover, and integrated monitoring dashboards. Zero-downtime architecture using blue-green deployments.',          1),
    (2, 1, 3, 720000, 32, 'Rejected',   'Hybrid approach with on-premise gateway and cloud analytics layer. Emphasis on security hardening and network segmentation beyond baseline.',                      1),
    (3, 2, 4, 375000, 20, 'Shortlisted', 'Modern React/Next.js portal with FHIR API integration, WCAG 2.1 AA compliance, and real‑time appointment scheduling. Full HIPAA audit trail.',                     1),
    (4, 2, 2, 390000, 22, 'Pending',     'AI‑driven patient triage with ML models for readmission risk, integrated into the portal UI. Compliance documentation still in review – missing HITRUST mapping.',  0),
    (5, 3, 2, 980000, 36, 'Shortlisted', 'End‑to‑end ML platform on Kubernetes with feature store, model registry, and A/B testing infrastructure. Real‑time inference via gRPC and Kafka.',                  1),
    (6, 3, 1, 1050000, 30, 'Pending',    'Serverless data lake on AWS with Kinesis, Glue, and SageMaker pipelines. Auto‑scaling inference endpoints using Lambda and ECS Fargate.',                         1),
    (7, 3, 5, 1025000, 34, 'Pending',    'Snowflake‑centric analytics with dbt transformations and embedded PowerBI. ML integration through Snowpark and external functions.',                             1);

-- ===== STATEMENTS OF WORK =====
INSERT OR IGNORE INTO statements_of_work (sow_id, project_id, vendor_id, total_budget, start_date, end_date, signed_date)
VALUES
    (1, 1, 1, 695000, '2025-04-01', '2025-10-15', '2025-03-18'),
    (2, 4, 3, 185000, '2024-07-15', '2024-12-31', '2024-07-01'),
    (3, 2, 4, 375000, '2025-05-01', '2025-09-30', '2025-04-10'),
    (4, 3, 2, 910000, '2025-08-01', '2026-03-31', '2025-07-15');

-- ===== MILESTONES =====
INSERT OR IGNORE INTO milestones (milestone_id, sow_id, milestone_name, description, planned_delivery_date, actual_delivery_date, status, payment_amount)
VALUES
    (1, 1, 'M1 – Current State Audit',              'Deep‑dive discovery of legacy ERP modules (finance, HR, supply chain), including data integrity checks and dependency mapping.',          '2025-05-15', '2025-05-19', 'Completed',    80000),
    (2, 1, 'M2 – Core Data Migration',               'Migrate 14 critical data tables to cloud PostgreSQL with full validation scripts and rollback plan. Includes automated reconciliation.', '2025-07-01', NULL,         'In-Progress', 175000),
    (3, 1, 'M3 – Integration & Performance Testing', 'End‑to‑end integration testing with 200+ test scenarios, load testing at 3x peak volume, and failover drills.',                        '2025-08-15', NULL,         'Pending',     150000),
    (4, 1, 'M4 – User Acceptance & Training',        'UAT with key stakeholders, creation of training materials, and parallel run with legacy system for 2 weeks.',                          '2025-09-15', NULL,         'Pending',     140000),
    (5, 1, 'M5 – Go‑Live & Warranty',                'Production cutover, hypercare support for 30 days, knowledge transfer to internal DevOps team.',                                      '2025-10-15', NULL,         'Pending',     150000),
    (6, 2, 'M1 – Security Baseline Assessment',       'Full vulnerability scan and penetration test of supplier portal APIs and backend services. Deliver risk‑ranked findings report.',       '2024-08-31', '2024-08-28', 'Completed',    60000),
    (7, 2, 'M2 – Critical Remediation',               'Remediate all critical and high‑severity findings; implement WAF rules and API rate limiting.',                                        '2024-10-15', '2024-10-20', 'Delayed',      75000),
    (8, 2, 'M3 – Compliance Evidence Package',        'Compile SOC2 Type II evidence, including access reviews, change management logs, and incident response runbooks.',                     '2024-12-15', '2024-12-10', 'Completed',    50000),
    (9, 3, 'M1 – Design Phase',                       'Finalize UI/UX mockups and accessibility compliance plan.',                                                                           '2025-06-01', NULL,         'In-Progress', 50000),
    (10, 4, 'M1 – Architecture Setup',                'Provision GPU cluster and setup MLOps pipelines.',                                                                                    '2025-09-01', NULL,         'Pending',     120000);

-- ===== PROJECT REQUIREMENTS =====
INSERT OR IGNORE INTO project_requirements (requirement_id, project_id, category, description, is_mandatory, priority)
VALUES
    (1,  1, 'Tech-Stack',  'Target architecture must be containerized on Kubernetes (EKS/AKS) with PostgreSQL 15+ and Redis as session store.',                                                              1, 'High'),
    (2,  1, 'Budget',      'Total implementation cost (including 12 months support) must not exceed $750,000.',                                                                                           1, 'High'),
    (3,  1, 'Compliance',  'Cloud provider must hold FedRAMP Moderate and SOC2 Type II certifications. All data at rest encrypted with AES‑256.',                                                          1, 'High'),
    (4,  2, 'Privacy',     'Full HIPAA compliance required – PHI encryption in transit and at rest, audit logging, and BAA with hosting provider.',                                                       1, 'High'),
    (5,  2, 'Tech-Stack',  'Frontend must be built with React 18+ and support server‑side rendering (Next.js) to meet SEO and performance goals.',                                                        1, 'Medium'),
    (6,  2, 'Compliance',  'Accessibility: WCAG 2.1 AA mandatory. Portal must pass automated axe‑core and manual screen‑reader testing.',                                                                 1, 'High'),
    (7,  3, 'Tech-Stack',  'ML platform must run on Kubernetes with support for multi‑tenant namespaces and GPU scheduling (NVIDIA A100 or equivalent).',                                                 1, 'High'),
    (8,  3, 'Budget',      'Phase 1 PoC budget capped at $250,000; must demonstrate 10k inference/min throughput with < 100ms p95 latency.',                                                             1, 'Medium'),
    (9,  3, 'Privacy',     'All customer‑facing data must comply with GDPR – data residency in EU region, right‑to‑erasure automation, and data protection impact assessment.',                            1, 'High'),
    (10, 3, 'Compliance',  'SOC2 Type I report must be achievable within 6 months of platform GA.',                                                                                                        1, 'Medium'),
    (11, 5, 'Tech-Stack',  'Dashboard must unify data from Shopify, Salesforce, and Snowflake into a single PowerBI embedded view with sub‑second tile refresh.',                                         1, 'High');

-- ===== MEETING TRANSCRIPTS (realistic multi‑turn conversations) =====
INSERT OR IGNORE INTO meeting_transcripts (transcript_id, project_id, meeting_date, raw_text, cleaned_summary, processing_status, meeting_type)
VALUES
    (1, 1, '2025-04-10 10:00:00',
     'Michael Chen (Aegis): Thanks for joining, everyone. We need to talk about the ERP cutover strategy. We can''t afford more than 4 hours of downtime – the supply chain team will riot.
Sarah (CloudForge): Understood. Blue‑green deployment plus a rollback plan gets us under 2 hours in our simulations. But we need access to the production load balancer a week earlier.
Anita (Aegis IT): That''s a problem – our change freeze starts May 1st. We can expedite an emergency RFC if you give us the exact IP lists and ports by end of this week.
Sarah: I''ll have my networking team deliver that by Thursday. Also, we discovered 3 data integrity issues in the HR module during the audit – duplicate SSNs, missing effective dates. We need your business owners to sign off on the cleansing rules.
Michael: Send the exceptions spreadsheet. HR Director will review by Monday. What about the finance module? Any surprises?
Sarah: Finance schema is cleaner, but we need to migrate 12 years of transaction history. Our estimate is 18 hours for the full extract – we''ll do it over a weekend with delta sync.
Anita: That conflicts with the month‑end close. Can we start on a Friday 6 PM and finish before Monday 6 AM?
Sarah: Yes, we can schedule it for May 16–18.
Michael: Good. Let''s lock that in. Next meeting we do a dry run of the rollback procedure.',
     'Kickoff detailed cutover planning. Key actions: CloudForge to deliver IP lists for RFC by Thursday; HR data cleansing rules sign‑off by Monday; finance migration scheduled for May 16–18 weekend.',
     'Pending', 'Kickoff'),

    (2, 1, '2025-05-20 14:00:00',
     'Sarah (CloudForge): We completed the core data migration last night. 13 out of 14 tables passed validation. The purchase_order_line_items table had 0.3% row count mismatch.
Anita (Aegis IT): What caused the mismatch?
Sarah: Our reconciliation log shows 412 rows dropped because of invalid foreign keys to a deprecated supplier table. We need a business decision – do we import them with nulls or exclude them?
Michael Chen (Aegis): Exclude them for cutover. We''ll deal with historical purchasing after go‑live. How are the performance tests looking?
Sarah: Load tests at 3x peak volume passed – response times under 800ms. We did uncover a connection pool leak in the API gateway under sustained load, but the fix is already in the pipeline.
Anita: When can we start integration testing?
Sarah: We''ll have the staging environment ready by Monday. I''ll send out a shared test plan with 220 scenarios. We''ll need at least two business users for UAT by June 10.
Michael: I''ll assign Susan from Finance and Mike from Supply Chain. Let''s aim for a full dress rehearsal on June 20.',
     'Data migration validation: 13/14 tables passed. 412 rows from purchase_order_line_items excluded due to legacy supplier FK. Load tests passed; connection pool leak fixed. Next: staging env ready Monday, UAT June 10, dress rehearsal June 20.',
     'Pending', 'Status Update'),

    (3, 2, '2025-03-20 15:00:00',
     'Dr. Lisa Abernathy (Wellspring): We need the portal to be fully accessible. Our patient population includes many elderly and visually impaired users. WCAG 2.1 AA is the floor, not the ceiling.
Tom (PixelByte): Agreed. We''ll build with semantic HTML, ARIA landmarks, and conduct manual screen‑reader testing with JAWS and NVDA every sprint. Are there specific color contrast thresholds you want beyond AA?
Dr. Abernathy: Yes, we want a contrast ratio of at least 7:1 for body text. Also, all video content must have closed captions and transcripts.
Elena (Wellspring Legal): From a compliance standpoint, we also need a full audit trail of every access to PHI. This includes search queries, appointment views, and prescription refills.
Tom: We can implement an immutable event log using AWS CloudTrail and a dedicated audit database. Each event will be hashed and timestamped.
Dr. Abernathy: That sounds robust. How will the portal integrate with our existing Epic EHR system?
Tom: We''ll use FHIR R4 APIs. We''ve already built a sandbox integration with synthetic data; we can demo it next week. The real challenge is mapping your custom document types.
Elena: We need a Business Associate Agreement (BAA) signed before any live data flows.
Tom: Understood. Our legal team will send the draft by Friday.',
     'Deep dive on accessibility (WCAG 2.1 AA + 7:1 contrast), PHI audit trail (immutable logs), FHIR integration with Epic EHR. BAA draft scheduled for Friday. Demo of FHIR sandbox next week.',
     'Pending', 'Requirements'),

    (4, 2, '2025-04-02 11:00:00',
     'Tom (PixelByte): We reviewed the RFP responses – two shops bid, but only CloudForge and DataPulse expressed interest. DataPulse proposed an AI‑powered triage feature.
Dr. Abernathy: I like the sound of AI triage, but we need to understand how it handles ambiguous symptoms. Is it FDA‑regulated?
Elena (Wellspring Legal): Most clinical decision support software is FDA Class II if it diagnoses. We need to check that. Also, the model must not exhibit bias against minority populations.
Tom: DataPulse said they''d use a validated risk score algorithm based on public health data, not a diagnosis. They''ll provide an algorithmic fairness audit. However, their HIPAA compliance mapping is incomplete – they''re still working on HITRUST alignment.
Dr. Abernathy: That''s a red flag. We can''t engage without full compliance documentation.
Tom: Agreed. That leaves CloudForge as the front‑runner, but they didn''t include AI features. We could partner for the base portal and later integrate a separate AI module.
Elena: Let''s shortlist CloudForge and set a final clarification call. If DataPulse can deliver the HITRUST report within two weeks, they stay in. Otherwise, we move forward without AI for now.',
     'Bid review: AI triage proposal by DataPulse promising but lacks HITRUST; must deliver documentation in two weeks. CloudForge shortlisted for core portal. Decision deferred for regulatory check on FDA classification.',
     'Pending', 'Vendor Evaluation'),

    (5, 3, '2025-06-18 09:30:00',
     'Arjun Mehta (NovaLogic): Our main pain point is model deployment. Data scientists wait weeks to get a REST endpoint. We need self‑service with guardrails.
Priya (DataPulse): That''s exactly what we propose – a model registry with CI/CD pipelines triggered by Git tags. The platform will auto‑generate Docker images and deploy to a staging namespace for testing.
Carlos (NovaLogic Infra): What about GPU scheduling? Our current cluster is a mess of taints and tolerations.
Priya: We''ll use Kueue for fair sharing and dynamic provisioning. We can also integrate with Spot Instances for cost savings on training jobs. The PoC will include a benchmark of 10k inference requests per minute using TensorFlow Serving.
Arjun: Good. Also, we need GDPR compliance for EU customers. How will you handle data residency?
Priya: The platform can be deployed across multiple AWS regions. We''ll configure the data catalog to tag and store EU data in Frankfurt. All pipelines will include a built‑in right‑to‑erasure workflow that triggers cascading deletes across storage layers.
Carlos: Can it handle streaming inference?
Priya: Yes, we''ll use Kafka for ingestion and gRPC for model serving, which gives us sub‑50ms latency. We can even do A/B testing with traffic splitting.
Arjun: That sounds promising. Let''s schedule a technical deep‑dive on the serving architecture for next week.',
     'Requirements for self‑service MLOps, GPU scheduling with Kueue, GDPR data residency (Frankfurt), streaming inference via Kafka/gRPC. PoC goal: 10k req/min benchmark. Deep‑dive scheduled.',
     'Pending', 'Technical Review'),

    (6, 3, '2025-07-08 14:00:00',
     'Arjun Mehta: We received the bids. DataPulse came in at $980k, CloudForge at $1.05M, and Nebula at $1.025M. Nebula''s architecture is Snowflake‑heavy, which might not suit our real‑time ML needs.
Priya (DataPulse): To clarify, our design uses Snowflake only for the analytics layer. Real‑time inference happens on a dedicated GPU cluster outside Snowflake.
Carlos: I like DataPulse''s approach, but $980k is still above our initial budget. Can we descope the A/B testing module for phase 1?
Priya: We could remove A/B testing and save about $70k, but you''d lose the ability to roll out models gradually. Alternatively, we can defer it to phase 2 and still deliver the feature store and model registry.
Arjun: Let''s do that. I also need assurance on the GDPR deletion workflow – our DPO wants an automated test within the first month.
Priya: Absolutely, we''ll include an automated compliance test suite as a milestone. If we win, we can start the architecture review sprint in August.
Arjun: Good. We''ll shortlist you and make a final decision after the technical deep‑dive.',
     'Bid evaluation: DataPulse descoped A/B testing to reduce cost to ~$910k. GDPR deletion test suite promised. Decision pending deep‑dive.',
     'DONE', 'Bid Evaluation'),

    (7, 5, '2025-05-12 10:00:00',
     'Sarah Whitman (Greenfield): We have data scattered across Shopify, Salesforce, and an on‑prem Snowflake warehouse. Our executives want a single pane of glass with real‑time sales funnel metrics.
Jenna (Solutions Architect): That''s a classic data mesh challenge. We can federate queries, but real‑time requires a semantic layer with caching. How fresh does the data need to be?
Sarah: The sales dashboard should update every minute. The inventory dashboard can be hourly.
Jenna: We''d need Change Data Capture (CDC) from Shopify and Salesforce into a streaming layer – probably Kafka. Then Snowflake can ingest via Snowpipe. PowerBI tiles can poll every 30 seconds.
Sarah: That sounds complex. What''s the ballpark cost?
Jenna: We''re still in Discovery, but I''d estimate between $300k and $450k for the full implementation. We can refine once we define the MVP features.
Sarah: Let''s schedule a workshop to map all the data sources and required KPIs.',
     'Discovery for omnichannel dashboard. Needs real‑time sales funnel (1 min) and hourly inventory. Proposed architecture: CDC to Kafka → Snowpipe → PowerBI. Estimated cost $300k‑$450k.',
     'PENDING', 'Discovery');

-- ===== EXTERNAL API MONITORS =====
INSERT OR IGNORE INTO external_api_monitors (monitor_id, project_id, site_url, uptime_status, last_checked)
VALUES
    (1, 1, 'https://erp-staging.aegisdynamics.com/health',            'UP',   '2025-04-25T10:00:00'),
    (2, 1, 'https://erp-api.aegisdynamics.com/v2/status',             'DOWN', '2025-04-25T09:55:00'),
    (3, 4, 'https://supplierportal.aegisdynamics.com/api/health',     'UP',   '2025-04-25T10:05:00'),
    (4, 2, 'https://patientportal-dev.wellspring.health/healthcheck', 'UP',   '2025-04-25T10:10:00');

-- ===== CHAT HISTORY (simulated support interactions) =====
INSERT OR IGNORE INTO chat_history (chat_id, project_id, user_id, message_content, ai_response, intent_identified, created_at)
VALUES
    (1, 1, 1, 'What is the current status of the Phoenix ERP project?',
     'Phoenix ERP Modernization is Active. Milestone M2 (Core Data Migration) is In-Progress; 13/14 tables passed validation. The next milestone is Integration Testing planned for 2025‑08‑15.',
     'project_status_query', '2025-05-21T08:30:00'),
    (2, 2, 1, 'Show me the RFP documents for Patient 360',
     'There is one RFP (ID 2) with a deadline of 2025‑04‑15 and a budget cap of $400,000. Currently three bids are under evaluation.',
     'rfp_lookup', '2025-04-02T13:00:00'),
    (3, 3, 1, 'Who are the vendors bidding for the AI Analytics Platform?',
     'Three vendors submitted bids: DataPulse AI ($980k), CloudForge Solutions ($1.05M), and Nebula Analytics ($1.025M). DataPulse is currently Shortlisted.',
     'vendor_list_query', '2025-07-09T09:15:00');

-- ===== CHAT THREADS & MESSAGES (multi‑turn conversation) =====
INSERT OR IGNORE INTO chat_threads (thread_id, user_id) VALUES ('thread-001', 1);
INSERT OR IGNORE INTO chat_messages (message_id, thread_id, role, content, created_at)
VALUES
    (1, 'thread-001', 'user',      'Can you send me the security assessment milestones for the Supply Chain project?', '2025-04-25T11:00:00'),
    (2, 'thread-001', 'assistant', 'Sure. Milestone M1 – Security Baseline Assessment was completed on 2024‑08‑28. M2 – Critical Remediation was delayed until 2024‑10‑20. M3 – Compliance Evidence Package was completed on 2024‑12‑10.', '2025-04-25T11:00:05'),
    (3, 'thread-001', 'user',      'Why was M2 delayed?', '2025-04-25T11:01:00'),
    (4, 'thread-001', 'assistant', 'The remediation required coordination with a third‑party WAF provider that had a change freeze, pushing the deadline by 5 days.', '2025-04-25T11:01:03');

-- ===== SECURITY EVENTS (sample audit logs) =====
INSERT OR IGNORE INTO security_events (event_id, event_type, username, ip_address, user_agent, details, created_at)
VALUES
    (1, 'LOGIN_SUCCESS', 'admin', '192.168.1.10', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 'Successful login from internal network.', '2025-04-25T08:00:00'),
    (2, 'LOGIN_FAILURE', 'admin', '203.0.113.42', 'python-requests/2.31.0', 'Failed login attempt – incorrect password.', '2025-04-25T09:45:00'),
    (3, 'PASSWORD_CHANGE', 'admin', '192.168.1.10', 'Mozilla/5.0', 'Admin password changed successfully.', '2025-04-25T10:00:00');

-- ===== PERMISSIONS =====
INSERT OR IGNORE INTO permissions (permission_id, permission_name, description)
VALUES
    (1, 'Financial Ledger Write', 'Ability to modify accounting ledgers and journals.'),
    (2, 'Production DB Admin', 'Full administrative access to production database clusters.'),
    (3, 'HR PII Access', 'Access to sensitive employee Personally Identifiable Information.'),
    (4, 'Cloud Infrastructure Edit', 'Modify cloud resources (EC2, S3, RDS).'),
    (5, 'Strategy Document Read', 'View internal strategic planning and roadmap documents.');

-- ===== ACCESS GAPS =====
INSERT OR IGNORE INTO access_gaps (user_id, project_id, permission_id, reason, severity, status, last_active)
VALUES
    (2, 4, 1, 'Project Phoenix marked as ''Completed'' on April 12. User still retains write access to financial modules.', 'high', 'flagged', '2025-04-25 14:20:00'),
    (3, 1, 2, 'User re-assigned to ''Project Orbit''. Phoenix ERP production admin access no longer required by policy.', 'medium', 'flagged', '2025-04-27 09:15:00'),
    (4, 2, 3, 'Temporary access for Legacy Audit expired on April 20. PII access remains active in IAM.', 'high', 'flagged', '2025-04-20 18:00:00'),
    (1, 5, 4, 'Executive oversight access granted during discovery phase. Phase completed, access should be restricted.', 'low', 'flagged', '2025-04-26 11:30:00');

-- ===== DASHBOARD METRICS =====
INSERT OR IGNORE INTO dashboard_metrics (metric_id, metric_key, status, reason, updated_at)
VALUES
    (1, 'active_project_count', 'GREEN', '4 projects currently active.', '2025-04-25T10:00:00'),
    (2, 'health_check', 'YELLOW', 'erp-api endpoint DOWN for Phoenix ERP.', '2025-04-25T10:00:00');

-- ===== MILESTONE TASKS =====
INSERT OR IGNORE INTO milestone_tasks (milestone_id, task_description, is_completed)
VALUES
    (1, 'Identify legacy ERP modules', 1),
    (1, 'Map data dependencies for Finance', 1),
    (1, 'Audit HR module data integrity', 1),
    (2, 'Setup staging PostgreSQL instance', 1),
    (2, 'Execute migration scripts for core tables', 0),
    (2, 'Run data reconciliation validation', 0),
    (6, 'Full vulnerability scan of APIs', 1),
    (6, 'Penetration test of supplier portal', 1),
    (6, 'Generate risk-ranked findings report', 1),
    (7, 'Implement WAF rules for top-tier threats', 0),
    (7, 'Apply API rate limiting across services', 1),
    (8, 'Compile SOC2 Type II evidence package', 1),
    (8, 'Finalize access review logs', 1),
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

    # Only seed if users table is empty to prevent data loss on accidental re-init
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    if user_count == 0:
        print("Seeding initial sample data...")
        conn.executescript(SEED_DATA)
        print("✓ Sample data seeded.")
    else:
        print(f"✓ Database already contains {user_count} users. Skipping seed.")

    # Verify
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"✓ Tables present: {tables}")

    conn.close()
    print("Database initialization complete.")


if __name__ == "__main__":
    init_database()