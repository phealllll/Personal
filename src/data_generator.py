import os
import time
import hmac
import hashlib
from pathlib import Path
import random
import shutil

BASE_DIR = Path(__file__).resolve().parent.parent
PAYLOAD_DIR = BASE_DIR / "landing_zone" / "payloads"
SIG_DIR = BASE_DIR / "landing_zone" / "signatures"

# Added security and it departments
DEPARTMENTS = ["Telemetry", "Accounting", "Human-Resources", "Security", "IT"]

PIPELINE_SECRET_KEY = b"nova_k101_zero_trust_key_9982"

def clean_slate():
    print("🧹 Sweeping old landing zones...")
    
    # Empty the contents of the payload directory without deleting the root folder
    if PAYLOAD_DIR.exists():
        for item in PAYLOAD_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
                
    # Empty the contents of the signatures directory
    if SIG_DIR.exists():
        for item in SIG_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()


def setup_directories():
    clean_slate()
    for dept in DEPARTMENTS:
        (PAYLOAD_DIR / dept).mkdir(parents=True, exist_ok=True)
        (SIG_DIR / dept).mkdir(parents=True, exist_ok=True)

def generate_hmac_signature(file_path):
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
    return hmac.new(PIPELINE_SECRET_KEY, file_bytes, hashlib.sha256).hexdigest()

def spawn_data(dept, num_rows=50):
    timestamp_base = int(time.time())
    filename = f"{dept}_batch_{timestamp_base}.csv"
    
    payload_path = PAYLOAD_DIR / dept / filename
    sig_path = SIG_DIR / dept / f"{filename}.sig"
    
    # 1. Generate Data into the file
    with open(payload_path, "w", encoding="utf-8") as f:
        if dept == "Telemetry":
            f.write("timestamp,asset_id,temperature_c,vibration_mm_s\n")
            for i in range(num_rows):
                # Increment time by 60 seconds per row for realistic sequential logs
                row_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp_base + (i * 60)))
                f.write(f"{row_time},K-101,{random.uniform(70, 95):.2f},{random.uniform(0.1, 5.0):.2f}\n")
                
        elif dept == "Accounting":
            f.write("invoice_id,vendor,cost_center,amount,currency\n")
            for i in range(num_rows):
                f.write(f"INV-{timestamp_base}-{i},TechCorp,IT-OPS,{random.uniform(100, 5000):.2f},CAD\n")
                
        elif dept == "Human-Resources":
            f.write("employee_id,department,action,timestamp\n")
            for i in range(num_rows):
                row_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp_base + (i * 3600)))
                action = random.choice(["FACILITY_ENTRY", "FACILITY_EXIT", "SYSTEM_LOGIN"])
                f.write(f"EMP-{random.randint(100,999)},HR,{action},{row_time}\n")
                
        elif dept == "Security":
            f.write("event_time,ip_address,login_status,username\n")
            for i in range(num_rows):
                row_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp_base + (i * 15)))
                status = random.choice(["SUCCESS", "FAILED", "LOCKED"])
                user = random.choice(["sysadmin", "operator_1", "guest", "service_account"])
                f.write(f"{row_time},192.168.1.{random.randint(10, 255)},{status},{user}\n")
                
        elif dept == "IT":
            f.write("ticket_id,system,issue,status\n")
            for i in range(num_rows):
                issue = random.choice(["HIGH_CPU", "MEMORY_LEAK", "NETWORK_DROP", "DISK_FULL"])
                status = random.choice(["OPEN", "IN_PROGRESS", "CLOSED", "RESOLVED"])
                f.write(f"INC-{random.randint(1000, 9999)},SERVER-0{random.randint(1, 9)},{issue},{status}\n")
        else:
            raise ValueError(f"🚨 CRITICAL: No data generation logic found for department: '{dept}'")

    # 2. Cryptographically Sign the Payload
    signature = generate_hmac_signature(payload_path)
    with open(sig_path, "w", encoding="utf-8") as f:
        f.write(signature)
        
    print(f"📡 [GENERATOR] Spawning {dept.upper()} data: {filename} ({num_rows} rows) (Signed & Secured)")
if __name__ == "__main__":
    setup_directories()
    print("--- Nova Cryptographic Generator Online ---")
    
    # Iterate through every department to guarantee generation for each
    for dept in DEPARTMENTS:
        spawn_data(dept)
        time.sleep(1)