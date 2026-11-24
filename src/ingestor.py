import csv
import hashlib
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from cv_verifier import verify_operative_scan
from db_connection import get_sql_connection


REQUIRED_COLUMNS = {
    "reading_id",
    "source_batch",
    "asset_id",
    "recorded_at_utc",
    "temperature_c",
    "vibration_mm_s",
    "handled_by_operative_id",
}
TEMP_ALERT_THRESHOLD = 90.0
VIB_ALERT_THRESHOLD = 7.0
QUARANTINE_DIR = Path(__file__).resolve().parent.parent / "data" / "quarantine"


def route_to_quarantine(csv_path: Path, manifest_path: Optional[Path], reason: str) -> None:
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if csv_path.exists():
        shutil.copy2(csv_path, QUARANTINE_DIR / f"{stamp}_{csv_path.name}")
    if manifest_path and manifest_path.exists():
        shutil.copy2(manifest_path, QUARANTINE_DIR / f"{stamp}_{manifest_path.name}")
    reason_file = QUARANTINE_DIR / f"{stamp}_{csv_path.stem}.error.txt"
    reason_file.write_text(reason, encoding="utf-8")


def log_dq_and_audit(
    status: str,
    check_name: str,
    detail: str,
    actor_id: Optional[str],
    username: str,
    role_name: str,
    action_performed: str,
    digest: str,
) -> None:
    with get_sql_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "{CALL api.usp_log_dq_check (?, ?, ?, ?, ?)}",
            (
                f"DQ-{uuid.uuid4().hex[:12].upper()}",
                "fact.telemetry_reading",
                check_name,
                status,
                detail[:500],
            ),
        )
        cursor.execute(
            "{CALL api.usp_append_audit_log (?, ?, ?, ?, ?, ?)}",
            (
                f"EVT-{uuid.uuid4().hex[:12].upper()}",
                actor_id,
                username,
                role_name,
                action_performed[:255],
                digest,
            ),
        )
        conn.commit()


def ingest_telemetry_batch(
    csv_path: Path,
    manifest_path: Path,
    prompt_cv_signoff: bool = True,
) -> dict:
    if not csv_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Missing telemetry CSV or manifest file.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_batch = manifest.get("source_batch", csv_path.stem)
    expected_sha256 = manifest.get("sha256", "")
    actual_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    if actual_sha256 != expected_sha256:
        reason = f"SHA256_MISMATCH expected={expected_sha256} actual={actual_sha256}"
        route_to_quarantine(csv_path, manifest_path, reason)
        log_dq_and_audit(
            "FAIL",
            "SHA256_MANIFEST_CHECK",
            reason,
            None,
            "nova_svc_user",
            "Service",
            f"REJECT_BATCH_SIGNATURE {source_batch}",
            actual_sha256,
        )
        return {
            "source_batch": source_batch,
            "status": "REJECTED_INVALID_SIGNATURE",
            "input_count": manifest.get("row_count", 0),
            "accepted_count": 0,
            "rejected_count": manifest.get("row_count", 0),
            "reason": reason,
        }

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing_cols = REQUIRED_COLUMNS - headers
        if missing_cols:
            reason = f"MISSING_REQUIRED_COLUMNS: {sorted(missing_cols)}"
            route_to_quarantine(csv_path, manifest_path, reason)
            log_dq_and_audit(
                "FAIL",
                "SCHEMA_CONTRACT_CHECK",
                reason,
                None,
                "nova_svc_user",
                "Service",
                f"REJECT_BATCH_SCHEMA {source_batch}",
                actual_sha256,
            )
            return {
                "source_batch": source_batch,
                "status": "REJECTED_MISSING_FIELDS",
                "input_count": 0,
                "accepted_count": 0,
                "rejected_count": 0,
                "reason": reason,
            }
        rows = list(reader)

    input_count = len(rows)
    if input_count == 0:
        reason = "EMPTY_BATCH_FILE"
        route_to_quarantine(csv_path, manifest_path, reason)
        return {
            "source_batch": source_batch,
            "status": "REJECTED_EMPTY",
            "input_count": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "reason": reason,
        }

    asset_id = rows[0]["asset_id"]
    operative_id = rows[0]["handled_by_operative_id"]
    accepted_count = 0
    rejected_count = 0
    breaches = []

    with get_sql_connection() as conn:
        cursor = conn.cursor()

        existing_batch_rows = cursor.execute(
            "SELECT COUNT(*) FROM fact.telemetry_reading WHERE source_batch = ?",
            (source_batch,),
        ).fetchone()[0]

        if existing_batch_rows > 0:
            reason = f"DUPLICATE_BATCH_DETECTED: {source_batch} already has {existing_batch_rows} rows"
            log_dq_and_audit(
                "WARN",
                "IDEMPOTENCY_REPEAT_CHECK",
                reason,
                operative_id,
                "nova_svc_user",
                "Service",
                f"SKIP_DUPLICATE_BATCH {source_batch}",
                actual_sha256,
            )
            return {
                "source_batch": source_batch,
                "status": "REJECTED_DUPLICATE_BATCH",
                "input_count": input_count,
                "accepted_count": 0,
                "rejected_count": input_count,
                "reason": reason,
            }

        asset_row = cursor.execute(
            "SELECT department_id FROM dim.asset WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if asset_row is None:
            raise ValueError(f"Unknown asset_id: {asset_id}")
        department_id = asset_row[0]

        op_row = cursor.execute(
            """
            SELECT e.username, r.role_name
            FROM dim.employee e
            JOIN dim.role r ON e.role_id = r.role_id
            WHERE e.employee_id = ?
            """,
            (operative_id,),
        ).fetchone()
        if op_row is None:
            raise ValueError(f"Unknown operative_id: {operative_id}")
        username, role_name = op_row

        for row in rows:
            try:
                if any(not row.get(col) for col in REQUIRED_COLUMNS):
                    rejected_count += 1
                    continue
                temp_c = float(row["temperature_c"])
                vib_mm_s = float(row["vibration_mm_s"])
                if vib_mm_s < 0:
                    rejected_count += 1
                    continue

                dup_id = cursor.execute(
                    "SELECT 1 FROM fact.telemetry_reading WHERE reading_id = ?",
                    (row["reading_id"],),
                ).fetchone()
                if dup_id:
                    rejected_count += 1
                    continue

                cursor.execute(
                    "{CALL api.usp_insert_telemetry_reading (?, ?, ?, ?, ?, ?, ?)}",
                    (
                        row["reading_id"],
                        row["asset_id"],
                        row["recorded_at_utc"],
                        temp_c,
                        vib_mm_s,
                        row["source_batch"],
                        row["handled_by_operative_id"],
                    ),
                )
                accepted_count += 1

                if temp_c > TEMP_ALERT_THRESHOLD or vib_mm_s > VIB_ALERT_THRESHOLD:
                    breaches.append((row["reading_id"], temp_c, vib_mm_s))
            except (ValueError, TypeError):
                rejected_count += 1

        dq_status = "PASS" if rejected_count == 0 else "WARN"
        cursor.execute(
            "{CALL api.usp_log_dq_check (?, ?, ?, ?, ?)}",
            (
                f"DQ-{uuid.uuid4().hex[:12].upper()}",
                "fact.telemetry_reading",
                "SHA256_MANIFEST_AND_SCHEMA_CHECK",
                dq_status,
                f"Batch {source_batch}: input={input_count}, accepted={accepted_count}, rejected={rejected_count}",
            ),
        )

        anomaly_id = None
        if breaches:
            anomaly_id = f"ANM-{uuid.uuid4().hex[:12].upper()}"
            max_temp = max(b[1] for b in breaches)
            max_vib = max(b[2] for b in breaches)
            cursor.execute(
                "{CALL api.usp_log_security_anomaly (?, ?, ?, ?, ?)}",
                (
                    anomaly_id,
                    asset_id,
                    department_id,
                    "HIGH",
                    f"{len(breaches)} threshold breaches in {source_batch} (max_temp={max_temp}C, max_vib={max_vib}mm/s)",
                ),
            )

        cursor.execute(
            "{CALL api.usp_append_audit_log (?, ?, ?, ?, ?, ?)}",
            (
                f"EVT-{uuid.uuid4().hex[:12].upper()}",
                operative_id,
                username,
                role_name,
                f"INGEST_BATCH {source_batch} in={input_count} acc={accepted_count} rej={rejected_count}",
                actual_sha256,
            ),
        )
        conn.commit()

    ver_result = None
    if prompt_cv_signoff and accepted_count > 0:
        ver_result = verify_operative_scan(
            employee_id=operative_id,
            asset_id=asset_id,
            source_batch=source_batch,
            anomaly_id=anomaly_id,
        )

    return {
        "source_batch": source_batch,
        "status": "INGESTED",
        "input_count": input_count,
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
        "breaches_flagged": len(breaches),
        "verification": ver_result,
    }


if __name__ == "__main__":
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    if len(sys.argv) > 1:
        csv_file = Path(sys.argv[1])
    else:
        csv_files = sorted(raw_dir.glob("BATCH-*.csv"))
        if not csv_files:
            raise FileNotFoundError("No batch CSV files found in data/raw/. Run src/data_generator.py first.")
        csv_file = csv_files[-1]

    manifest_file = csv_file.with_suffix(".manifest.json")
    summary = ingest_telemetry_batch(csv_file, manifest_file, prompt_cv_signoff=True)
    print(summary)