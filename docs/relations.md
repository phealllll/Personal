```markdown
# NovaWarehouse Data Model, Entity Relationships & Lineage Specification

Related Diagram: `docs/erd_diagram.png`  
Physical DDL Implementation: `sql/01_schema_nova.sql`  
Database Engine: Microsoft SQL Server (`NovaWarehouse`)

---

## 1. Architectural Overview & Schema Separation

`NovaWarehouse` follows a Kimball-inspired Dimensional Star Schema augmented with Zero-Trust Operational Audit Schemas and a Stored Procedure Security Boundary. All database objects are isolated into four logical schemas:

| Schema | Purpose | Direct Table Access (`nova_svc_user`) | Direct Table Access (`nova_dash_user`) |
| :--- | :--- | :--- | :--- |
| `dim` | Master reference entities (departments, RBAC roles, employees, biometric templates, industrial assets) | `SELECT` only | `SELECT` only |
| `fact` | High-volume immutable telemetry measurements, threshold anomaly alerts, and biometric verification events | `SELECT` on `telemetry_reading` only | `SELECT` only |
| `ops` | Data quality validation logs and append-only security audit ledger | `DENIED` (must call `api.usp_*`) | `SELECT` only |
| `api` | Parameterized stored procedures (`api.usp_*`) enforcing business logic, referential integrity, and auditing | `EXECUTE` granted | `DENIED` |

---

## 2. Visual Entity-Relationship Diagram (`docs/erd_diagram.png`)

Place your exported ERD image at `docs/erd_diagram.png` so it renders directly below:

![NovaWarehouse Entity-Relationship Diagram](erd_diagram.png)

---

## 3. Detailed Table & Attribute Specifications

### 3.1 Dimension Schema (`dim`)

#### `dim.department`
Organizational units owning industrial infrastructure assets and personnel.
* Primary Key: `department_id` (`VARCHAR(20)`) — e.g., `DEPT-OPS`, `DEPT-SEC`.
* Attributes: `department_name` (`VARCHAR(100)`, `UNIQUE`), `cost_center` (`VARCHAR(30)`), `created_at_utc` (`DATETIME2(3)`).

#### `dim.role`
Zero-trust authorization roles governing operational privileges.
* Primary Key: `role_id` (`VARCHAR(20)`) — e.g., `ROLE-OP`, `ROLE-MGR`, `ROLE-AUD`.
* Attributes: `role_name` (`VARCHAR(50)`, `UNIQUE` — `Field Operative`, `Telemetry Manager`, `Security Auditor`), `access_level` (`INT` — `1` to `3`), `can_approve_anomalies` (`BIT`).

#### `dim.employee`
Authorized personnel roster mapped to departments and security roles.
* Primary Key: `employee_id` (`VARCHAR(20)`) — e.g., `EMP-001` through `EMP-004`.
* Foreign Keys:
  * `role_id` $\rightarrow$ `dim.role(role_id)`
  * `department_id` $\rightarrow$ `dim.department(department_id)`
* Attributes: `username` (`VARCHAR(50)`, `UNIQUE`), `full_name` (`VARCHAR(120)`), `is_active` (`BIT`), `hired_at_utc` (`DATETIME2(3)`).

#### `dim.employee_biometric`
Stores mathematical facial representations for enrolled operatives without retaining raw images.
* Primary Key: `biometric_id` (`VARCHAR(32)`) — e.g., `BIO-2DE52C34EF3C`.
* Foreign Key (1:1 Unique): `employee_id` (`VARCHAR(20)`, `UNIQUE`) $\rightarrow$ `dim.employee(employee_id)`
* Attributes:
  * `embedding_json` (`NVARCHAR(MAX)`) — JSON-serialized 128-element float32 SFace vector.
  * `model_version` (`VARCHAR(50)`) — e.g., `sface_2021dec`.
  * `enrolled_at_utc` (`DATETIME2(3)`).

#### `dim.asset`
Monitored industrial machinery generating telemetry streams.
* Primary Key: `asset_id` (`VARCHAR(24)`) — e.g., `ASSET-CMP-01`.
* Foreign Keys:
  * `department_id` $\rightarrow$ `dim.department(department_id)`
  * `assigned_operative_id` $\rightarrow$ `dim.employee(employee_id)`
* Attributes: `asset_name` (`VARCHAR(100)`), `asset_type` (`VARCHAR(50)`), `location_code` (`VARCHAR(50)`), `status` (`VARCHAR(20)`).

---

### 3.2 Fact Schema (`fact`)

#### `fact.telemetry_reading`
Grain: One sensor observation per compressor asset per timestamp.
* Primary Key: `reading_id` (`VARCHAR(32)`).
* Foreign Keys:
  * `asset_id` $\rightarrow$ `dim.asset(asset_id)`
  * `handled_by_operative_id` $\rightarrow$ `dim.employee(employee_id)`
  * `verification_id` (`VARCHAR(32)`, nullable until webcam sign-off completes) $\rightarrow$ `fact.operative_verification(verification_id)`
* Measures & Metadata: `recorded_at_utc` (`DATETIME2(3)`), `temperature_c` (`DECIMAL(6,2)`), `vibration_mm_s` (`DECIMAL(6,3)`), `source_batch` (`VARCHAR(64)` — indexed for idempotency checks), `ingested_at_utc` (`DATETIME2(3)`).

#### `fact.security_anomaly`
Grain: One threshold breach incident per batch per asset.
* Primary Key: `anomaly_id` (`VARCHAR(32)`).
* Foreign Keys:
  * `asset_id` $\rightarrow$ `dim.asset(asset_id)`
  * `department_id` $\rightarrow$ `dim.department(department_id)`
  * `verified_by_operative_id` (`VARCHAR(20)`, nullable) $\rightarrow$ `dim.employee(employee_id)`
* Attributes: `severity` (`VARCHAR(20)` — `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), `description` (`VARCHAR(500)`), `detected_at_utc` (`DATETIME2(3)`), `resolved_flag` (`BIT`), `resolved_at_utc` (`DATETIME2(3)`).

#### `fact.operative_verification`
Grain: One live facial verification scan event.
* Primary Key: `verification_id` (`VARCHAR(32)`).
* Foreign Keys:
  * `employee_id` $\rightarrow$ `dim.employee(employee_id)`
  * `asset_id` $\rightarrow$ `dim.asset(asset_id)`
  * `anomaly_id` (`VARCHAR(32)`, nullable) $\rightarrow$ `fact.security_anomaly(anomaly_id)`
* Attributes: `source_batch` (`VARCHAR(64)`), `cv_confidence_score` (`DECIMAL(6,4)`), `auth_status` (`VARCHAR(20)` — `VERIFIED` or `REJECTED`), `frame_sha256` (`CHAR(64)`), `verified_at_utc` (`DATETIME2(3)`).

---

### 3.3 Operational Governance Schema (`ops`)

#### `ops.dq_validation_log`
Records schema contract, SHA-256 manifest, and batch idempotency outcomes.
* Primary Key: `check_id` (`VARCHAR(32)`).
* Attributes: `checked_at_utc` (`DATETIME2(3)`), `table_name` (`VARCHAR(100)`), `check_name` (`VARCHAR(100)`), `status` (`VARCHAR(20)` — `PASS`, `WARN`, `FAIL`), `detail` (`VARCHAR(500)`).

#### `ops.audit_ledger`
Append-only operational ledger protected by explicit `DENY UPDATE, DELETE` permissions.
* Primary Key: `event_id` (`VARCHAR(32)`).
* Foreign Key (Nullable for rejected anonymous/tampered batches): `employee_id` $\rightarrow$ `dim.employee(employee_id)`
* Attributes: `event_timestamp_utc` (`DATETIME2(3)`), `username` (`VARCHAR(50)`), `role_name` (`VARCHAR(50)`), `action_performed` (`VARCHAR(255)`), `query_hash` (`CHAR(64)`).

---

## 4. Entity-Relationship Cardinality Matrix

| Parent Entity | Child Entity | Cardinality | Foreign Key Column | Referential Behavior & Business Rule |
| :--- | :--- | :--- | :--- | :--- |
| `dim.department` | `dim.employee` | `1 : N` | `dim.employee.department_id` | Every employee belongs to exactly one department |
| `dim.department` | `dim.asset` | `1 : N` | `dim.asset.department_id` | Every industrial asset is owned by one department |
| `dim.department` | `fact.security_anomaly` | `1 : N` | `fact.security_anomaly.department_id` | Anomalies route to the owning department for escalation |
| `dim.role` | `dim.employee` | `1 : N` | `dim.employee.role_id` | Governs RBAC authorization and anomaly approval rights |
| `dim.employee` | `dim.employee_biometric` | `1 : 0..1` | `dim.employee_biometric.employee_id` | Each employee has at most one active 128-D facial template (`UNIQUE`) |
| `dim.employee` | `fact.telemetry_reading` | `1 : N` | `fact.telemetry_reading.handled_by_operative_id` | Tracks accountability for who handled the sensor batch |
| `dim.employee` | `fact.operative_verification` | `1 : N` | `fact.operative_verification.employee_id` | Links every webcam scan to the claimed employee identity |
| `dim.asset` | `fact.telemetry_reading` | `1 : N` | `fact.telemetry_reading.asset_id` | Star-schema dimension join for compressor time-series analytics |
| `dim.asset` | `fact.security_anomaly` | `1 : N` | `fact.security_anomaly.asset_id` | Associates temperature/vibration breaches with specific equipment |
| `fact.security_anomaly` | `fact.operative_verification` | `0..1 : N` | `fact.operative_verification.anomaly_id` | Optional link when biometric scan resolves an open threshold breach |
| `fact.operative_verification` | `fact.telemetry_reading` | `0..1 : N` | `fact.telemetry_reading.verification_id` | Attests all telemetry rows in `source_batch` upon `VERIFIED` scan |

---

## 5. End-to-End Data Lineage & Write Flow (`api.usp_*`)

No application script writes directly to base tables. Every state mutation flows through parameterized stored procedures in the `api` schema:

1. Batch Ingestion (`api.usp_insert_telemetry_reading`): Inserts validated CSV observations into `fact.telemetry_reading` with `verification_id = NULL`.
2. Data Quality Logging (`api.usp_log_dq_check`): Writes batch reconciliation counts (`input`, `accepted`, `rejected`) or quarantine failure reasons into `ops.dq_validation_log`.
3. Anomaly Flagging (`api.usp_log_security_anomaly`): Triggered automatically by `src/ingestor.py` whenever `temperature_c > 90.0` or `vibration_mm_s > 7.0`, inserting an unresolved alert (`resolved_flag = 0`) into `fact.security_anomaly`.
4. Biometric Attestation (`api.usp_record_operative_verification`): Executed by `src/cv_verifier.py` after cosine similarity evaluation. When `auth_status = 'VERIFIED'`, the procedure atomically:
   * Inserts the scan record and `frame_sha256` into `fact.operative_verification`.
   * Backfills `verification_id` onto all rows in `fact.telemetry_reading` matching `source_batch`.
   * Marks the linked `fact.security_anomaly` record as resolved (`resolved_flag = 1`, `verified_by_operative_id = @employee_id`).
5. Immutable Audit Trail (`api.usp_append_audit_log`): Appends a tamper-evident ledger entry into `ops.audit_ledger` recording the actor, role, action, and SHA-256 digest.