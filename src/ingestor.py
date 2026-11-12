import duckdb
import hmac
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import uuid
import shutil

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"
SIG_DIR = BASE_DIR / "landing_zone" / "signatures"
PIPELINE_SECRET_KEY = b"nova_k101_zero_trust_key_9982"


DATA_CONTRACTS = {
    "telemetry": {"table": "bronze_telemetry", "columns": ["timestamp", "asset_id", "temperature_c", "vibration_mm_s"]},
    "accounting": {"table": "bronze_accounting", "columns": ["invoice_id", "vendor", "cost_center", "amount", "currency"]},
    "human-resources": {"table": "bronze_hr", "columns": ["employee_id", "department", "action", "timestamp"]},
    "security": {"table": "bronze_security", "columns": ["event_time", "ip_address", "login_status", "username"]},
    "it": {"table": "bronze_it", "columns": ["ticket_id", "system", "issue", "status"]}
}
def verify_file_integrity(payload_path, department):
    """Compares the live file hash against the detached signature file."""
    sig_path = SIG_DIR / department / f"{payload_path.name}.sig"
    
    if not sig_path.exists():
        raise FileNotFoundError(f"Missing cryptographic signature for {payload_path.name}")
        
    with open(sig_path, 'r', encoding="utf-8") as f:
        expected_hash = f.read().strip()
        
    with open(payload_path, 'rb') as f:
        file_bytes = f.read()
            
    actual_hash = hmac.new(PIPELINE_SECRET_KEY, file_bytes, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(expected_hash, actual_hash):
        raise ValueError(f"CRITICAL: Hash mismatch! {payload_path.name} was tampered with or corrupted.")
    
    return True

def process_secure_payload(file_path):
    department = file_path.parent.name.lower()
    
    if department not in DATA_CONTRACTS:
        print(f"⚠️ [SECURITY DROP] Rejected: '{department}'")
        return
        
    try:
        # 1. Cryptographic Verification
        verify_file_integrity(file_path, department)
        print(f"🔒 [VERIFIED] Cryptographic signature valid for {file_path.name}")
        
        # 2. Database Contract Execution
        con = duckdb.connect(str(DB_PATH))
        contract = DATA_CONTRACTS[department]
        target_table = contract["table"]
        
        file_str = str(file_path).replace('\\', '/')
        headers = con.execute(f"SELECT * FROM read_csv_auto('{file_str}') LIMIT 0").df().columns.tolist()
        
        missing_columns = set(contract["columns"]) - set(headers)
        if missing_columns:
            raise ValueError(f"Schema violation. Missing columns: {missing_columns}")
      
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS {target_table} AS 
            SELECT *, 'placeholder' as batch_id, CURRENT_TIMESTAMP as ingested_at 
            FROM read_csv_auto('{file_str}') LIMIT 0;
            
            INSERT INTO {target_table}
            SELECT *, '{file_path.name}' as batch_id, CURRENT_TIMESTAMP as ingested_at 
            FROM read_csv_auto('{file_str}', all_varchar=1);
        """)
        
        rows_inserted = con.execute(f"SELECT count(*) FROM read_csv_auto('{file_str}', all_varchar=1)").fetchone()[0]
        print(f"✅ [INGESTED] {file_path.name} securely loaded {rows_inserted} rows into {target_table}.")
        
        # 3. RUN ANOMALY DETECTOR AFTER INGESTION
        if department == "telemetry":
            run_anomaly_detector(con)
            
    except Exception as e:
        # 4. DEAD-LETTER QUEUE (Quarantine Bad Files)
        print(f"🚨 [QUARANTINE ALERT] Failed to process {file_path.name}. Reason: {e}")
        
        # Physically move the tampered/bad file to a secure quarantine folder
        quarantine_dir = BASE_DIR / "landing_zone" / "quarantine"
        quarantine_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            shutil.move(str(file_path), str(quarantine_dir / file_path.name))
            print(f"📦 [DLQ] File moved to {quarantine_dir}")
        except Exception as move_error:
            print(f"⚠️ [DLQ ERROR] Could not move file: {move_error}")
            
    finally:
        if 'con' in locals():
            con.close()

def run_anomaly_detector(con):
    try:
        df = con.execute("SELECT * FROM bronze_telemetry").df()
        if df.empty or 'temperature_c' not in df.columns: return

        temps = df['temperature_c'].astype(float)
        mean, std = np.mean(temps), np.std(temps)

        if std > 0:
            df['z_score'] = (temps - mean) / std
            anomalies = df[abs(df['z_score']) > 2.5] 

            for _, row in anomalies.iterrows():
                anomaly_id = str(uuid.uuid4())
                desc = f"Thermal anomaly: {row['temperature_c']}°C at asset {row.get('asset_id', 'unknown')}"
                con.execute(
                    "INSERT INTO security_anomalies (anomaly_id, department, severity, description) SELECT ?, 'telemetry', 'HIGH', ? WHERE NOT EXISTS (SELECT 1 FROM security_anomalies WHERE description = ?)",
                    [anomaly_id, desc, desc]
                )
        print("Anomaly scan complete.")
    except Exception as e:
        print(f"Anomaly check skipped: {e}")
        
if __name__ == "__main__":
    print("🚀 Booting Nova Zero-Trust Ingestor...")
    
    try:
        target_dir = BASE_DIR / "landing_zone"
        
        # Recursively find all CSVs, specifically excluding the signatures directory
        pending_files = [f for f in target_dir.rglob("*.csv") if "signatures" not in f.parts]
        
        if not pending_files:
            print(f"📭 No new CSV files found in: {target_dir}")
        else:
            print(f"📦 Found {len(pending_files)} payloads. Initiating secure ingestion...")
            for payload in pending_files:
                process_secure_payload(payload)
                
            print("🏁 Pipeline execution complete.")
            
    except Exception as e:
        print(f"❌ Critical Execution Error: {e}")