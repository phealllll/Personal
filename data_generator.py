import csv
import hmac
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

HMAC_SECRET = b"nova_industrial_secure_key_2026"

def generate_compressor_data(num_rows=250, inject_anomaly=False):
    print(f"Generating a clean batch of {num_rows} sensor readings for K-101...")
    
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=num_rows)
    
    # Ensure separate directories exist
    Path('data').mkdir(exist_ok=True)
    Path('signatures').mkdir(exist_ok=True)
    
    timestamp_str = end_time.strftime("%Y%m%d_%H%M%S")
    status_tag = "anomaly" if inject_anomaly else "normal"
    base_filename = f'k101_sensor_{timestamp_str}_{status_tag}'
    
    file_path = Path('data') / f'{base_filename}.csv'
    sig_path = Path('signatures') / f'{base_filename}.csv.hmac'
    
    csv_content = [
        ['timestamp', 'asset_id', 'temperature_c', 'pressure_psi', 'vibration_mm_s', 'power_kw', 'is_anomalous']
    ]
    
    current_time = start_time
    for _ in range(num_rows):
        temp = 85.0
        pressure = 120.0
        vibration = 4.5
        power = 450.0
        is_anomalous = 0
        
        if inject_anomaly:
            is_anomalous = 1
            power *= 1.3
            vibration *= 1.4
            
        csv_content.append([
            current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'K-101',
            round(temp, 2),
            round(pressure, 2),
            round(vibration, 3),
            round(power, 2),
            is_anomalous
        ])
        current_time += timedelta(minutes=1)
        
    # Write CSV to data/
    with open(file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(csv_content)
        
    # Compute HMAC and write signature to the isolated signatures/ folder
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
        
    signature = hmac.new(HMAC_SECRET, file_bytes, hashlib.sha256).hexdigest()
    
    with open(sig_path, 'w') as sig_file:
        sig_file.write(signature)
        
    print(f"Success! CSV saved to: {file_path}")
    print(f" [SECURE ISOLATION] Signature saved to: {sig_path}")

if __name__ == "__main__":
    generate_compressor_data(num_rows=250, inject_anomaly=False)