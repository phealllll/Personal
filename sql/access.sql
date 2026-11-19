USE NovaWarehouse;
GO

CREATE OR ALTER PROCEDURE api.usp_insert_telemetry_reading
    @reading_id VARCHAR(64),
    @asset_id VARCHAR(32),
    @recorded_at_utc DATETIME2,
    @temperature_c DECIMAL(10, 4),
    @vibration_mm_s DECIMAL(10, 4),
    @source_batch VARCHAR(128),
    @handled_by_operative_id VARCHAR(32)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (
        SELECT 1
        FROM dim.employee e
        JOIN dim.role r ON e.role_id = r.role_id
        WHERE e.employee_id = @handled_by_operative_id
          AND r.role_name = 'Operative'
    )
    BEGIN
        THROW 50001, 'Unauthorized: Only active Operatives can submit telemetry readings.', 1;
    END

    INSERT INTO fact.telemetry_reading (
        reading_id, asset_id, recorded_at_utc, temperature_c,
        vibration_mm_s, source_batch, handled_by_operative_id
    )
    VALUES (
        @reading_id, @asset_id, @recorded_at_utc, @temperature_c,
        @vibration_mm_s, @source_batch, @handled_by_operative_id
    );
END
GO

CREATE OR ALTER PROCEDURE api.usp_record_operative_verification
    @verification_id VARCHAR(64),
    @employee_id VARCHAR(32),
    @asset_id VARCHAR(32),
    @anomaly_id VARCHAR(64) = NULL,
    @source_batch VARCHAR(128) = NULL,
    @cv_confidence_score DECIMAL(5, 4),
    @auth_status VARCHAR(20),
    @frame_sha256 CHAR(64)
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRANSACTION;

    BEGIN TRY
        IF NOT EXISTS (
            SELECT 1
            FROM dim.employee e
            JOIN dim.role r ON e.role_id = r.role_id
            JOIN dim.employee_biometric b ON e.employee_id = b.employee_id
            WHERE e.employee_id = @employee_id
              AND r.role_name = 'Operative'
              AND b.is_active = 1
        )
        BEGIN
            THROW 50002, 'Biometric Gate Denied: Employee is not an active enrolled Operative.', 1;
        END

        INSERT INTO fact.operative_verification (
            verification_id, employee_id, asset_id, anomaly_id,
            source_batch, cv_confidence_score, auth_status, frame_sha256
        )
        VALUES (
            @verification_id, @employee_id, @asset_id, @anomaly_id,
            @source_batch, @cv_confidence_score, @auth_status, @frame_sha256
        );

        IF @auth_status = 'VERIFIED'
        BEGIN
            IF @source_batch IS NOT NULL
            BEGIN
                UPDATE fact.telemetry_reading
                SET verification_id = @verification_id
                WHERE asset_id = @asset_id
                  AND source_batch = @source_batch
                  AND handled_by_operative_id = @employee_id
                  AND verification_id IS NULL;
            END

            IF @anomaly_id IS NOT NULL
            BEGIN
                UPDATE fact.security_anomaly
                SET verified_by_operative_id = @employee_id,
                    resolved_flag = 1
                WHERE anomaly_id = @anomaly_id;
            END
        END

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE api.usp_append_audit_log
    @event_id VARCHAR(64),
    @employee_id VARCHAR(32) = NULL,
    @username VARCHAR(100),
    @role_name VARCHAR(64),
    @action_performed VARCHAR(255),
    @query_hash CHAR(64)
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO ops.audit_ledger (
        event_id, employee_id, username, role_name, action_performed, query_hash
    )
    VALUES (
        @event_id, @employee_id, @username, @role_name, @action_performed, @query_hash
    );
END
GO

CREATE ROLE nova_service_role;
CREATE ROLE nova_auditor_role;
CREATE ROLE nova_dashboard_reader;
GO

GRANT EXECUTE ON SCHEMA::api TO nova_service_role;
GRANT SELECT ON SCHEMA::dim TO nova_service_role;
GRANT SELECT ON SCHEMA::fact TO nova_service_role;

DENY INSERT, UPDATE, DELETE ON SCHEMA::dim TO nova_service_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::fact TO nova_service_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::ops TO nova_service_role;

GRANT SELECT ON SCHEMA::dim TO nova_dashboard_reader;
GRANT SELECT ON SCHEMA::fact TO nova_dashboard_reader;
GRANT SELECT ON SCHEMA::ops TO nova_dashboard_reader;
DENY INSERT, UPDATE, DELETE, EXECUTE ON DATABASE::NovaWarehouse TO nova_dashboard_reader;

GRANT SELECT ON SCHEMA::dim TO nova_auditor_role;
GRANT SELECT ON SCHEMA::fact TO nova_auditor_role;
GRANT SELECT ON SCHEMA::ops TO nova_auditor_role;

DENY UPDATE, DELETE ON ops.audit_ledger TO PUBLIC, nova_service_role, nova_auditor_role, nova_dashboard_reader;
GO