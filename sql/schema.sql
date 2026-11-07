
-- NOVA ENTERPRISE LAKEHOUSE & SECURITY HUB
-- Database Schema Definition (DuckDB)


-- 1. Identity & Access Management (IAM)
CREATE TABLE IF NOT EXISTS iam_users (
    username VARCHAR UNIQUE,
    role VARCHAR,
    salt VARCHAR,
    password_hash VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Operations (Telemetry)
CREATE TABLE IF NOT EXISTS bronze_telemetry (
    timestamp VARCHAR,
    asset_id VARCHAR,
    temperature_c VARCHAR,
    vibration_mm_s VARCHAR,
    batch_id VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Finance (Accounting)
CREATE TABLE IF NOT EXISTS bronze_accounting (
    invoice_id VARCHAR,
    vendor VARCHAR,
    cost_center VARCHAR,
    amount VARCHAR,
    currency VARCHAR,
    batch_id VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Human Resources (HR)
CREATE TABLE IF NOT EXISTS bronze_hr (
    employee_id VARCHAR,
    department VARCHAR,
    action VARCHAR,
    timestamp VARCHAR,
    batch_id VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Cyber Security
CREATE TABLE IF NOT EXISTS bronze_security (
    event_time VARCHAR,
    ip_address VARCHAR,
    login_status VARCHAR,
    username VARCHAR,
    batch_id VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Information Technology (IT)
CREATE TABLE IF NOT EXISTS bronze_it (
    ticket_id VARCHAR,
    system VARCHAR,
    issue VARCHAR,
    status VARCHAR,
    batch_id VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);