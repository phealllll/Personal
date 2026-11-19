IF DB_ID(N'NovaWarehouse') IS NULL
BEGIN
    CREATE DATABASE NovaWarehouse;
END
GO

USE NovaWarehouse;
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'dim') EXEC(N'CREATE SCHEMA dim');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'fact') EXEC(N'CREATE SCHEMA fact');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ops') EXEC(N'CREATE SCHEMA ops');
GO
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'api') EXEC(N'CREATE SCHEMA api');
GO

CREATE TABLE dim.department (
    department_id VARCHAR(32) NOT NULL PRIMARY KEY,
    department_name VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE dim.unit (
    unit_id VARCHAR(32) NOT NULL PRIMARY KEY,
    unit_name VARCHAR(64) NOT NULL UNIQUE,
    department_id VARCHAR(32) NOT NULL,
    CONSTRAINT FK_unit_department FOREIGN KEY (department_id) REFERENCES dim.department(department_id)
);

CREATE TABLE dim.role (
    role_id VARCHAR(32) NOT NULL PRIMARY KEY,
    role_name VARCHAR(64) NOT NULL UNIQUE
);

CREATE TABLE dim.employee (
    employee_id VARCHAR(32) NOT NULL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    department_id VARCHAR(32) NOT NULL,
    unit_id VARCHAR(32) NULL,
    role_id VARCHAR(32) NOT NULL,
    manager_id VARCHAR(32) NULL,
    telemetry_manager_id VARCHAR(32) NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_employee_department FOREIGN KEY (department_id) REFERENCES dim.department(department_id),
    CONSTRAINT FK_employee_unit FOREIGN KEY (unit_id) REFERENCES dim.unit(unit_id),
    CONSTRAINT FK_employee_role FOREIGN KEY (role_id) REFERENCES dim.role(role_id),
    CONSTRAINT FK_employee_manager FOREIGN KEY (manager_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT FK_employee_telemetry_manager FOREIGN KEY (telemetry_manager_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT CHK_employee_not_self_manager CHECK (manager_id IS NULL OR manager_id <> employee_id),
    CONSTRAINT CHK_employee_not_self_tm CHECK (telemetry_manager_id IS NULL OR telemetry_manager_id <> employee_id)
);

CREATE TABLE dim.employee_biometric (
    biometric_id VARCHAR(32) NOT NULL PRIMARY KEY,
    employee_id VARCHAR(32) NOT NULL UNIQUE,
    encoding_version VARCHAR(32) NOT NULL DEFAULT 'OPENCV_LBPH_V1',
    reference_sha256 CHAR(64) NOT NULL,
    encoding_payload VARBINARY(MAX) NOT NULL,
    is_active BIT NOT NULL DEFAULT 1,
    enrolled_at_utc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_biometric_employee FOREIGN KEY (employee_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT CHK_biometric_sha256_len CHECK (LEN(reference_sha256) = 64)
);

CREATE TABLE dim.asset (
    asset_id VARCHAR(32) NOT NULL PRIMARY KEY,
    asset_name VARCHAR(120) NOT NULL,
    asset_type VARCHAR(64) NOT NULL,
    department_id VARCHAR(32) NOT NULL,
    assigned_operative_id VARCHAR(32) NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT FK_asset_department FOREIGN KEY (department_id) REFERENCES dim.department(department_id),
    CONSTRAINT FK_asset_operative FOREIGN KEY (assigned_operative_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT CHK_asset_status CHECK (status IN ('ACTIVE', 'MAINTENANCE', 'OFFLINE', 'DECOMMISSIONED'))
);

CREATE TABLE fact.security_anomaly (
    anomaly_id VARCHAR(64) NOT NULL PRIMARY KEY,
    asset_id VARCHAR(32) NOT NULL,
    department_id VARCHAR(32) NOT NULL,
    detected_at_utc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    severity VARCHAR(20) NOT NULL,
    description VARCHAR(500) NOT NULL,
    verified_by_operative_id VARCHAR(32) NULL,
    resolved_flag BIT NOT NULL DEFAULT 0,
    CONSTRAINT FK_anomaly_asset FOREIGN KEY (asset_id) REFERENCES dim.asset(asset_id),
    CONSTRAINT FK_anomaly_department FOREIGN KEY (department_id) REFERENCES dim.department(department_id),
    CONSTRAINT FK_anomaly_operative FOREIGN KEY (verified_by_operative_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT CHK_anomaly_severity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
);

CREATE TABLE fact.operative_verification (
    verification_id VARCHAR(64) NOT NULL PRIMARY KEY,
    employee_id VARCHAR(32) NOT NULL,
    asset_id VARCHAR(32) NOT NULL,
    anomaly_id VARCHAR(64) NULL,
    source_batch VARCHAR(128) NULL,
    verified_at_utc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    cv_confidence_score DECIMAL(5, 4) NOT NULL,
    auth_status VARCHAR(20) NOT NULL,
    frame_sha256 CHAR(64) NOT NULL,
    CONSTRAINT FK_verification_employee FOREIGN KEY (employee_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT FK_verification_asset FOREIGN KEY (asset_id) REFERENCES dim.asset(asset_id),
    CONSTRAINT FK_verification_anomaly FOREIGN KEY (anomaly_id) REFERENCES fact.security_anomaly(anomaly_id),
    CONSTRAINT CHK_cv_confidence CHECK (cv_confidence_score >= 0.0000 AND cv_confidence_score <= 1.0000),
    CONSTRAINT CHK_verification_auth_status CHECK (auth_status IN ('VERIFIED', 'REJECTED', 'DENIED_ROLE')),
    CONSTRAINT CHK_verification_sha256_len CHECK (LEN(frame_sha256) = 64)
);

CREATE TABLE fact.telemetry_reading (
    reading_id VARCHAR(64) NOT NULL PRIMARY KEY,
    asset_id VARCHAR(32) NOT NULL,
    recorded_at_utc DATETIME2 NOT NULL,
    temperature_c DECIMAL(10, 4) NOT NULL,
    vibration_mm_s DECIMAL(10, 4) NOT NULL,
    source_batch VARCHAR(128) NOT NULL,
    handled_by_operative_id VARCHAR(32) NULL,
    verification_id VARCHAR(64) NULL,
    ingested_at_utc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_telemetry_asset FOREIGN KEY (asset_id) REFERENCES dim.asset(asset_id),
    CONSTRAINT FK_telemetry_operative FOREIGN KEY (handled_by_operative_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT FK_telemetry_verification FOREIGN KEY (verification_id) REFERENCES fact.operative_verification(verification_id),
    CONSTRAINT CHK_telemetry_vibration CHECK (vibration_mm_s >= 0)
);

CREATE TABLE ops.audit_ledger (
    event_id VARCHAR(64) NOT NULL PRIMARY KEY,
    event_timestamp_utc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    employee_id VARCHAR(32) NULL,
    username VARCHAR(100) NOT NULL,
    role_name VARCHAR(64) NOT NULL,
    action_performed VARCHAR(255) NOT NULL,
    query_hash CHAR(64) NOT NULL,
    CONSTRAINT FK_audit_employee FOREIGN KEY (employee_id) REFERENCES dim.employee(employee_id),
    CONSTRAINT CHK_audit_sha256_len CHECK (LEN(query_hash) = 64)
);

CREATE TABLE ops.dq_validation_log (
    check_id VARCHAR(64) NOT NULL PRIMARY KEY,
    checked_at_utc DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    table_name VARCHAR(128) NOT NULL,
    check_name VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    detail VARCHAR(500) NOT NULL,
    CONSTRAINT CHK_dq_status CHECK (status IN ('PASS', 'WARN', 'FAIL'))
);
GO