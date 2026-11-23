import csv
import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def generate_telemetry_batch(
    row_count: int = 250,
    asset_id: str = "ASSET-CMP-01",
    operative_id: str = "EMP-003",
    seed: int = 42,
) -> tuple[Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    batch_id = f"BATCH-{asset_id}-{stamp}"
    csv_path = DATA_DIR / f"{batch_id}.csv"
    manifest_path = DATA_DIR / f"{batch_id}.manifest.json"

    base_time = datetime.now(timezone.utc) - timedelta(minutes=row_count)
    fieldnames = [
        "reading_id",
        "source_batch",
        "asset_id",
        "recorded_at_utc",
        "temperature_c",
        "vibration_mm_s",
        "handled_by_operative_id",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i in range(row_count):
            is_spike = i in (47, 132, 219)
            temp_c = round(rng.uniform(92.0, 104.5) if is_spike else rng.uniform(62.0, 78.5), 4)
            vib_mm_s = round(rng.uniform(7.5, 11.2) if is_spike else rng.uniform(1.2, 4.1), 4)
            rec_time = (base_time + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")

            writer.writerow(
                {
                    "reading_id": f"RDG-{uuid.uuid4().hex[:12].upper()}",
                    "source_batch": batch_id,
                    "asset_id": asset_id,
                    "recorded_at_utc": rec_time,
                    "temperature_c": temp_c,
                    "vibration_mm_s": vib_mm_s,
                    "handled_by_operative_id": operative_id,
                }
            )

    file_sha256 = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest = {
        "source_batch": batch_id,
        "csv_filename": csv_path.name,
        "row_count": row_count,
        "sha256": file_sha256,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Generated {row_count} rows -> {csv_path}")
    print(f"SHA-256 Digest -> {file_sha256}")
    return csv_path, manifest_path


if __name__ == "__main__":
    generate_telemetry_batch()