import csv
import hmac
import hashlib
from pathlib import Path
import duckdb

HMAC_SECRET = b"nova_industrial_secure_key_2026"

def verify_and_ingest():
    db_path = "nova_warehouse.duckdb"
    con = duckdb.connect(db_path)
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS k101_sensor_logs (
            timestamp TIMESTAMP,
            asset_id VARCHAR,
            temperature_c DOUBLE,
            pressure_psi DOUBLE,
            vibration_mm_s DOUBLE,
            power_kw DOUBLE,
            is_anomalous INTEGER,
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
    
    data_dir = Path('data')
    sig_dir = Path('signatures')
    csv_files = list(data_dir.glob('k101_sensor_*.csv'))
    
    for file in csv_files:
        print(f"\nAnalyzing security profile for: {file.name}")
        
        # Point to the isolated signatures folder, mapping the filename
        sig_path = sig_dir / f"{file.name}.hmac"
        
        try:
            if not sig_path.exists():
                raise FileNotFoundError(f"Isolated signature missing in /signatures for {file.name}! Potential tampering.")
                
            with open(file, 'rb') as f:
                file_bytes = f.read()
                
            with open(sig_path, 'r') as sig_file:
                expected_sig = sig_file.read().strip()
                
            computed_sig = hmac.new(HMAC_SECRET, file_bytes, hashlib.sha256).hexdigest()
            
            if not hmac.compare_digest(computed_sig, expected_sig):
                raise ValueError(f"HMAC cryptographic signature mismatch for {file.name} against isolated vault signature.")
            
            print(" [PASS] Cross-vault cryptographic signature verified.")

            with open(file, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                
                expected_header = ['timestamp', 'asset_id', 'temperature_c', 'pressure_psi', 'vibration_mm_s', 'power_kw', 'is_anomalous']
                if header != expected_header:
                    raise ValueError(f"Schema mismatch detected in {file.name}.")
                
                row_count = 0
                for row in reader:
                    temp = float(row[2])
                    if temp < -50 or temp > 200:
                        raise ValueError(f"Out-of-bounds telemetry detected: {temp}C.")
                    row_count += 1
                    
            file_str = str(file).replace('\\', '/')
            con.execute(f"""
                INSERT INTO k101_sensor_logs (timestamp, asset_id, temperature_c, pressure_psi, vibration_mm_s, power_kw, is_anomalous)
                SELECT timestamp, asset_id, temperature_c, pressure_psi, vibration_mm_s, power_kw, is_anomalous
                FROM read_csv_auto('{file_str}')
            """)
            
            con.execute("INSERT INTO ingestion_audit_log (batch_id, status, rows_processed) VALUES (?, ?, ?)", 
                        [file.name, "SUCCESS", row_count])
            print(f" [SECURE] Batch {file.name} successfully cross-verified and ingested ({row_count} rows).")
            
        except Exception as e:
            print(f" [SECURITY ALERT] Ingestion failed for {file.name}. Reason: {e}")
            con.execute("INSERT INTO ingestion_audit_log (batch_id, status, rows_processed) VALUES (?, ?, ?)", 
                        [file.name, f"REJECTED: {str(e)}", 0])

    total_rows = con.execute("SELECT COUNT(*) FROM k101_sensor_logs").fetchone()[0]
    print(f"\nTotal rows now in DuckDB warehouse: {total_rows}")

    con.close()

if __name__ == "__main__":
    verify_and_ingest()