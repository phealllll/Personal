import csv
import hashlib
import json
import uuid
from pathlib import Path
from cv_verifier import verify_operative_scan
from db_connection import get_sql_connection


TEMP_ALERT_THRESHOLD = 90.0
VIB_ALERT_THRESHOLD = 7.0


def verify_file_integrity(csv_path: Path, manifest_path: Path) -> dict:
    if not csv_path.exists() or not manifest_path.exists():
        raise FileNotFoundError("Missing telemetry CSV or manifest file.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    if actual_sha256 != manifest["sha256"]:
        raise RuntimeError(
            f"Integrity check failed for {csv_path.name}: expected {manifest['sha256']}, got {actual_sha256}"
        )
    return manifest


def ingest_telemetry_batch(csv_path: Path, manifest_path: Path, prompt_cv_signoff: bool = True) -> None:
    manifest = verify_file_integrity(csv_path, manifest_path)
    source_batch = manifest["source_batch"]
    file_sha256 = manifest["sha256"]

    with csv_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != manifest["row_count"]:
        raise ValueError(f"Row count mismatch: manifest={manifest['row_count']}, actual={len(rows)}")

    asset_id = rows[0]["asset_id"]
    operative_id = rows[0]["handled_by_operative_id"]
    breaches = []

    with get_sql_connection() as conn:
        cursor = conn.cursor()

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
            temp_c = float(row["temperature_c"])
            vib_mm_s = float(row["vibration_mm_s"])
            if vib_mm_s < 0:
                raise ValueError(f"Negative vibration in {row['reading_id']}")

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

            if temp_c > TEMP_ALERT_THRESHOLD or vib_mm_s > VIB_ALERT_THRESHOLD:
                breaches.append((row["reading_id"], temp_c, vib_mm_s))

        cursor.execute(
            "{CALL api.usp_log_dq_check (?, ?, ?, ?, ?)}",
            (
                f"DQ-{uuid.uuid4().hex[:12].upper()}",
                "fact.telemetry_reading",
                "SHA256_MANIFEST_AND_SCHEMA_CHECK",
                "PASS",
                f"Batch {source_batch} verified ({len(rows)} rows, sha256={file_sha256[:16]}...)",
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
                f"INGEST_BATCH {source_batch} rows={len(rows)} breaches={len(breaches)}",
                file_sha256,
            ),
        )
        conn.commit()

    print(f"Ingested {len(rows)} rows for {source_batch} | Breaches flagged: {len(breaches)}")

    if prompt_cv_signoff:
        print("Launching biometric verification to attest batch and clear anomalies...")
        ver_result = verify_operative_scan(
            employee_id=operative_id,
            asset_id=asset_id,
            source_batch=source_batch,
            anomaly_id=anomaly_id,
        )
        print("Biometric Attestation Result:", ver_result)


if __name__ == "__main__":
    from data_generator import generate_telemetry_batch

    csv_file, manifest_file = generate_telemetry_batch()
    ingest_telemetry_batch(csv_file, manifest_file, prompt_cv_signoff=True)