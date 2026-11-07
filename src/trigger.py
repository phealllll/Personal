import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ingestor import process_secure_payload

BASE_DIR = Path(__file__).resolve().parent.parent
PAYLOAD_DIR = BASE_DIR / "landing_zone" / "payloads"

class EnterpriseLandingZoneHandler(FileSystemEventHandler):
    def process_event(self, file_path_str):
        file_path = Path(file_path_str)
        
        # Ignore directories or non-CSV files
        if file_path.is_dir() or file_path.suffix != '.csv':
            return
            
        department = file_path.parent.name.upper()
        print(f"\n[WATCHDOG] 📂 File detected in {department} zone: {file_path.name}")
        
        # Prevent read collisions by waiting for the file copy/write to finish
        self.wait_until_ready(file_path)
        process_secure_payload(file_path)

    def on_created(self, event):
        # Triggers when a file is created directly
        self.process_event(event.src_path)
        
    def on_moved(self, event):
        # Triggers if a file is atomically renamed (e.g., .tmp to .csv)
        self.process_event(event.dest_path)

    def wait_until_ready(self, file_path):
        historical_size = -1
        while True:
            try:
                if not file_path.exists():
                    return
                current_size = file_path.stat().st_size
                if current_size == historical_size and current_size > 0:
                    break
                historical_size = current_size
                time.sleep(0.5)
            except Exception:
                time.sleep(0.5)

def start_watchdog():
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"🚀 [NOVA WATCHDOG] Online. Recursively monitoring zero-trust landing zones...")
    print("📡 Listening for payloads: TELEMETRY | ACCOUNTING | HR | SECURITY | IT")
    print("--- Press Ctrl+C to terminate ---")
    
    event_handler = EnterpriseLandingZoneHandler()
    observer = Observer()
    # recursive=True automatically watches all department subfolders inside /payloads/
    observer.schedule(event_handler, str(PAYLOAD_DIR), recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[NOVA WATCHDOG] Offline.")
    observer.join()

if __name__ == "__main__":
    start_watchdog()