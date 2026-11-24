import csv
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
import pyodbc
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
load_dotenv(PROJECT_ROOT / ".env")

from data_generator import generate_telemetry_batch
from ingestor import ingest_telemetry_batch
from db_connection import get_sql_connection


EVIDENCE_DIR = PROJECT_ROOT / "evidence"


def test_rbac_restrictions() -> list[str]:
    logs = []
    with get_sql_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM ops.audit_ledger;")
            logs.append("FAIL: nova_svc_login was able to DELETE from ops.audit_ledger")
        except pyodbc.Error as exc:
            logs.append(f"PASS [RBAC Service Delete Denied]: {exc.args[0]}")

        try:
            cursor.execute(
                "INSERT INTO fact.telemetry_reading (reading_id, asset_id, recorded_at_utc, temperature_c, vibration_mm_s, source_batch, handled_by_operative_id) VALUES ('TEST-DIRECT', 'ASSET-CMP-01', SYSUTCDATETIME(), 70.0, 2.0, 'DIRECT', 'EMP-003');"
            )
            logs.append("FAIL: nova_svc_login bypassed stored procedure for direct INSERT")
        except pyodbc.Error as exc:
            logs.append(f"PASS [RBAC Direct Table Insert Denied]: {exc.args[0]}")

    server = os.getenv("NOVA_SQL_SERVER", "PHEAL")
    database = os.getenv("NOVA_SQL_DB", "NovaWarehouse")
    driver = os.getenv("NOVA_SQL_DRIVER", "{ODBC Driver 18 for SQL Server}")
    dash_user = os.getenv("NOVA_DASH_USER", "nova_dash_login")
    dash_pwd = os.getenv("NOVA_DASH_PASSWORD", "")

    dash_conn_str = (
        f"DRIVER={driver};SERVER={server};DATABASE={database};"
        f"UID={dash_user};PWD={dash_pwd};Encrypt=yes;TrustServerCertificate=yes;"
    )
    with pyodbc.connect(dash_conn_str, autocommit=True) as dconn:
        dcur = dconn.cursor()
        try:
            dcur.execute(
                "{CALL api.usp_log_dq_check ('DQ-HACK', 'fact.telemetry_reading', 'TEST', 'PASS', 'HACK')}"
            )
            logs.append("FAIL: Read-only dashboard user executed stored procedure")
        except pyodbc.Error as exc:
            logs.append(f"PASS [RBAC Dashboard Execute Denied]: {exc.args[0]}")

    return logs


def run_all_tests() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    report_lines = ["=== NOVAWAREHOUSE AIDA 1145 PIPELINE & SECURITY VERIFICATION ==="]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        csv_ok, man_ok = generate_telemetry_batch(row_count=15, seed=99)
        res_ok = ingest_telemetry_batch(csv_ok, man_ok, prompt_cv_signoff=False)
        report_lines.append(f"\n[Test 1 - Valid Batch Ingestion]\n{json.dumps(res_ok, indent=2)}")

        res_dup = ingest_telemetry_batch(csv_ok, man_ok, prompt_cv_signoff=False)
        report_lines.append(f"\n[Test 2 - Repeat Ingestion Idempotency]\n{json.dumps(res_dup, indent=2)}")

        tampered_csv = tmp / "tampered.csv"
        tampered_csv.write_text(csv_ok.read_text(encoding="utf-8") + "\nEXTRA_TAMPERED_LINE", encoding="utf-8")
        res_tamper = ingest_telemetry_batch(tampered_csv, man_ok, prompt_cv_signoff=False)
        report_lines.append(f"\n[Test 3 - Invalid SHA-256 Signature & Quarantine]\n{json.dumps(res_tamper, indent=2)}")

        missing_csv = tmp / "missing_cols.csv"
        with missing_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["reading_id", "asset_id", "temperature_c"])
            writer.writerow(["RDG-BAD-001", "ASSET-CMP-01", "72.5"])
        missing_man = tmp / "missing_cols.manifest.json"
        missing_man.write_text(
            json.dumps(
                {
                    "source_batch": "BATCH-MISSING-COLS-001",
                    "row_count": 1,
                    "sha256": hashlib.sha256(missing_csv.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        res_missing = ingest_telemetry_batch(missing_csv, missing_man, prompt_cv_signoff=False)
        report_lines.append(f"\n[Test 4 - Missing Required Columns & Quarantine]\n{json.dumps(res_missing, indent=2)}")

    rbac_results = test_rbac_restrictions()
    report_lines.append("\n[Test 5 - SQL Server Zero-Trust RBAC Enforcement]")
    report_lines.extend(rbac_results)

    report_text = "\n".join(report_lines)
    print(report_text)
    (EVIDENCE_DIR / "aida1145_test_report.txt").write_text(report_text, encoding="utf-8")


if __name__ == "__main__":
    run_all_tests()