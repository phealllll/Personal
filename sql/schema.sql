-- ==========================================================
-- NOVA K-101 INDUSTRIAL TELEMETRY & SECURITY WAREHOUSE
-- Database Schema Definition (DuckDB)
-- ==========================================================

-- 1. Identity & Access Management (IAM) Table
CREATE TABLE IF NOT EXISTS iam_users (
    username VARCHAR UNIQUE,
    role VARCHAR,
    salt VARCHAR,
    password_hash VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bronze Layer: Raw, untyped multi-source ingestion
CREATE TABLE IF NOT EXISTS bronze_telemetry (
    timestamp VARCHAR,
    asset_id VARCHAR,
    temperature_c VARCHAR,
    pressure_psi VARCHAR,
    vibration_mm_s VARCHAR,
    power_kw VARCHAR,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    batch_id VARCHAR
);

-- 3. Ingestion & Cryptographic Audit Log
CREATE TABLE IF NOT EXISTS ingestion_audit_log (
    batch_id VARCHAR,
    status VARCHAR,
    rows_processed INTEGER,
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Operational Maintenance Logs
CREATE TABLE IF NOT EXISTS maintenance_logs (
    log_id VARCHAR,
    asset_id VARCHAR,
    technician VARCHAR,
    action_taken VARCHAR,
    parts_replaced VARCHAR,
    logged_at TIMESTAMP
);

-- 5. Silver Layer View (Cleaned & Typed)
CREATE OR REPLACE VIEW silver_telemetry AS
SELECT 
    TRY_CAST(timestamp AS TIMESTAMP) as timestamp,
    asset_id,
    COALESCE(TRY_CAST(temperature_c AS DOUBLE), 85.0) as temperature_c,
    TRY_CAST(REPLACE(pressure_psi, ' PSI', '') AS DOUBLE) as pressure_psi,
    TRY_CAST(vibration_mm_s AS DOUBLE) as vibration_mm_s,
    TRY_CAST(power_kw AS DOUBLE) as power_kw,
    batch_id
FROM bronze_telemetry
WHERE TRY_CAST(vibration_mm_s AS DOUBLE) < 900.0;

-- 6. Gold Layer View (Business Aggregations)
CREATE OR REPLACE VIEW gold_daily_asset_health AS
SELECT 
    asset_id,
    CAST(timestamp AS DATE) as operating_date,
    AVG(temperature_c) as avg_temp,
    MAX(pressure_psi) as max_pressure,
    COUNT(*) as readings_count
FROM silver_telemetry
GROUP BY asset_id, CAST(timestamp AS DATE);