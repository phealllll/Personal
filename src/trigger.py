import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ingestor import run_etl_pipeline

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / 'data'

class TelemetryHandler(FileSystemEventHandler):
    def on_created(self, event):
        
        if event.is_directory or not event.src_path.endswith('.csv'):
            return
        
        file_path = Path(event.src_path)
        print(f"\n[WATCHDOG] 🚨 Edge telemetry detected: {file_path.name}")
        
        
        self.wait_until_ready(file_path)
        
        print(f"[WATCHDOG] Lock released. Triggering Medallion ETL Pipeline...")
        run_etl_pipeline()
        print(f"[WATCHDOG] 💤 Ingestion complete. Returning to standby.")

    def wait_until_ready(self, file_path):
        """Checks file size repeatedly until it stops growing (meaning the copy is finished)."""
        historical_size = -1
        while True:
            try:
                current_size = file_path.stat().st_size
                # If size hasn't changed in 1 second and is greater than 0, it is ready
                if current_size == historical_size and current_size > 0:
                    break
                historical_size = current_size
                time.sleep(1)
            except Exception:
                
                time.sleep(1)

def start_watchdog():
    DATA_DIR.mkdir(exist_ok=True)
    print(f"🚀 [NOVA WATCHDOG] Online. Actively monitoring {DATA_DIR.name}/ for instantaneous ingestion...")
    
    event_handler = TelemetryHandler()
    observer = Observer()
    observer.schedule(event_handler, str(DATA_DIR), recursive=False)
    observer.start()
    
    try:
        while True:
            time.sleep(1) # Keeps the main thread alive while Watchdog runs in the background
    except KeyboardInterrupt:
        observer.stop()
        print("\n[NOVA WATCHDOG] Offline. Automated ingestion halted.")
    observer.join()

if __name__ == "__main__":
    start_watchdog()