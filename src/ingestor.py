import hmac
import hashlib
from pathlib import Path
import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "nova_warehouse.duckdb"
DATA_DIR = BASE_DIR / 'data'
SIG_DIR = BASE_DIR / 'signatures'

HMAC_SECRET = b"nova_industrial_secure_key_2026"

def setup_warehouse(con):
    """Creates the target tables if they do not exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS k101_sensor_logs (
            timestamp TIMESTAMP,
            asset_id VARCHAR,
            temperature_c DOUBLE,
            pressure_psi DOUBLE,
            vibration_mm_s DOUBLE,
            power_kw DOUBLE,
            is_anomalous INTEGER DEFAULT 0,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            log_id VARCHAR,
            asset_id VARCHAR,
            technician VARCHAR,
            action_taken VARCHAR,
            parts_replaced VARCHAR,
            logged_at TIMESTAMP,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_audit_log (
            batch_id VARCHAR,
            status VARCHAR,
            rows_processed INTEGER,
            verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def verify_cryptography(file_path):
    """Enforces zero-trust cross-vault verification."""
    sig_path = SIG_DIR / f"{file_path.name}.hmac"
    if not sig_path.exists():
        raise FileNotFoundError(f"Missing cryptographic signature in /signatures for {file_path.name}")
        
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
        
    with open(sig_path, 'r') as sig_file:
        expected_sig = sig_file.read().strip()
        
    computed_sig = hmac.new(HMAC_SECRET, file_bytes, hashlib.sha256).hexdigest()
    
    if not hmac.compare_digest(computed_sig, expected_sig):
        raise ValueError(f"HMAC cryptographic signature mismatch for {file_path.name}.")

def run_etl_pipeline():
    con = duckdb.connect(str(DB_PATH))
    setup_warehouse(con)
    
    csv_files = list(DATA_DIR.glob('*.csv'))
    
    for file in csv_files:
        print(f"\nProcessing: {file.name}")
        
        # 1. Idempotency Check
        existing_audit = con.execute(
            "SELECT status FROM ingestion_audit_log WHERE batch_id = ? AND status = 'SUCCESS'",
            [file.name]
        ).fetchone()
        
        if existing_audit:
            print(f" [SKIPPED] Batch {file.name} already ingested.")
            continue
            
        try:
            # 2. Security Check (HMAC Verification)
            verify_cryptography(file)
            print(" [PASS] Cryptographic signature verified.")
            
            file_str = str(file).replace('\\', '/')
            
            # 3. ETL Transformation & Loading
            if file.name.startswith("telemetry_"):
                # Use TRY_CAST to safely handle empty strings and dirty data without crashing
                con.execute(f"""
                    INSERT INTO k101_sensor_logs (timestamp, asset_id, temperature_c, pressure_psi, vibration_mm_s, power_kw)
                    SELECT 
                        TRY_CAST(timestamp AS TIMESTAMP),
                        asset_id,
                        COALESCE(TRY_CAST(temperature_c AS DOUBLE), 85.0), -- Safely catches '' and makes it 85.0
                        TRY_CAST(REPLACE(CAST(pressure_psi AS VARCHAR), ' PSI', '') AS DOUBLE), 
                        TRY_CAST(vibration_mm_s AS DOUBLE),
                        TRY_CAST(power_kw AS DOUBLE)
                    FROM read_csv_auto('{file_str}')
                    WHERE TRY_CAST(vibration_mm_s AS DOUBLE) < 900.0 
                """)
                rows = con.execute("SELECT count(*) FROM read_csv_auto(?)", [file_str]).fetchone()[0]
            elif file.name.startswith("maintenance_"):
                con.execute(f"""
                    INSERT INTO maintenance_logs (log_id, asset_id, technician, action_taken, parts_replaced, logged_at)
                    SELECT * FROM read_csv_auto('{file_str}')
                """)
                rows = con.execute("SELECT count(*) FROM read_csv_auto(?)", [file_str]).fetchone()[0]
                
            else:
                raise ValueError("Unknown file schema.")

            con.execute("INSERT INTO ingestion_audit_log (batch_id, status, rows_processed) VALUES (?, ?, ?)", 
                        [file.name, "SUCCESS", rows])
            print(f" [SECURE ETL] Batch {file.name} cleaned and loaded ({rows} rows).")
            
        except Exception as e:
            print(f" [ALERT] Pipeline failed for {file.name}. Reason: {e}")
            con.execute("INSERT INTO ingestion_audit_log (batch_id, status, rows_processed) VALUES (?, ?, ?)", 
                        [file.name, f"REJECTED: {str(e)}", 0])

    con.close()

if __name__ == "__main__":
    run_etl_pipeline()