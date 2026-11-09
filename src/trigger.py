from pathlib import Path
from ingestor import process_secure_payload

BASE_DIR = Path(__file__).resolve().parent.parent
PAYLOAD_DIR = BASE_DIR / "landing_zone" / "payloads"

def run_batch_ingestion():
    print("🚀 [NOVA BATCH INGESTOR] Scanning landing zones for payloads...")
    
    # Recursively find all CSV files inside the payloads folder
    pending_files = list(PAYLOAD_DIR.rglob("*.csv"))
    
    if not pending_files:
        print("📭 No files found in landing zones. Exiting.")
        return
        
    print(f"📦 Found {len(pending_files)} files. Starting cryptographic ingestion...\n")
    
    for file_path in pending_files:
        print(f"Processing: {file_path.parent.name.upper()} / {file_path.name}")
        process_secure_payload(file_path)
        
    print("\n✅ [BATCH COMPLETE] Warehouse updated.")

if __name__ == "__main__":
    run_batch_ingestion()