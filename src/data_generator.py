import csv
import hmac
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import random

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'
SIG_DIR = BASE_DIR / 'signatures'

HMAC_SECRET = b"nova_industrial_secure_key_2026"

def secure_and_save(file_path, csv_content):
    """Writes the CSV and generates the isolated HMAC sidecar."""
    with open(file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(csv_content)
        
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
        
    signature = hmac.new(HMAC_SECRET, file_bytes, hashlib.sha256).hexdigest()
    sig_path = SIG_DIR / f'{file_path.name}.hmac'
    
    with open(sig_path, 'w') as sig_file:
        sig_file.write(signature)
        
    print(f" [EDGE SIM] Written: {file_path.name} | Security Sidecar: {sig_path.name}")

def generate_messy_telemetry(num_rows=250):
    """Generates K-101 telemetry with intentional data corruption for ETL transformation."""
    DATA_DIR.mkdir(exist_ok=True)
    SIG_DIR.mkdir(exist_ok=True)
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = DATA_DIR / f'telemetry_k101_{timestamp_str}.csv'
    
    csv_content = [['timestamp', 'asset_id', 'temperature_c', 'pressure_psi', 'vibration_mm_s', 'power_kw']]
    current_time = datetime.now() - timedelta(minutes=num_rows)
    
    for i in range(num_rows):
        temp = 85.0 + random.uniform(-0.8, 0.8)
        pressure = 120.0 + random.uniform(-1.5, 1.5)
        vibration = 4.2 + random.uniform(-0.2, 0.2)
        power = 450.0 + random.uniform(-3.0, 3.0)
        
        # --- INJECTING DIRTY DATA FOR ETL SHOWCASE ---
        # 1. Null values (Simulating sensor dropouts)
        if random.random() < 0.05: temp = "" 
        
        # 2. String artifacts (Simulating bad firmware formatting)
        if random.random() < 0.10: pressure = f"{round(pressure, 2)} PSI" 
        else: pressure = round(pressure, 2)
            
        # 3. Extreme outliers (To be filtered out in SQL)
        if random.random() < 0.02: vibration = 999.99 
        
        csv_content.append([
            current_time.strftime('%Y-%m-%d %H:%M:%S'),
            'K-101',
            temp if temp == "" else round(temp, 2),
            pressure,
            round(vibration, 3),
            round(power, 2)
        ])
        current_time += timedelta(minutes=1)
        
    secure_and_save(file_path, csv_content)

def generate_maintenance_logs():
    """Generates a secondary data source from the reliability department."""
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = DATA_DIR / f'maintenance_k101_{timestamp_str}.csv'
    
    csv_content = [['log_id', 'asset_id', 'technician', 'action_taken', 'parts_replaced', 'logged_at']]
    
    technicians = ["john_operator", "sarah_engineer"]
    actions = ["Replaced O-ring", "Calibrated thermal sensor", "Lubricated bearings", "Routine inspection"]
    
    for i in range(5):
        csv_content.append([
            f"MNT-{random.randint(1000, 9999)}",
            'K-101',
            random.choice(technicians),
            random.choice(actions),
            "Yes" if random.random() > 0.5 else "No",
            (datetime.now() - timedelta(hours=random.randint(1, 48))).strftime('%Y-%m-%d %H:%M:%S')
        ])
        
    secure_and_save(file_path, csv_content)

if __name__ == "__main__":
    print("Initializing Multi-Source Edge Simulation...")
    generate_messy_telemetry(num_rows=250)
    generate_maintenance_logs()