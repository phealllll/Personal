import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

def generate_compressor_data(num_rows=250, inject_anomaly=False):
    print(f"Generating a clean batch of {num_rows} sensor readings for K-101...")
    
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=num_rows)
    
    # Ensure the data folder exists using pathlib
    Path('data').mkdir(exist_ok=True)
    
    timestamp_str = end_time.strftime("%Y%m%d_%H%M%S")
    status_tag = "anomaly" if inject_anomaly else "normal"
    file_path = f'data/k101_sensor_{timestamp_str}_{status_tag}.csv'
    
    with open(file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['timestamp', 'asset_id', 'temperature_c', 'pressure_psi', 'vibration_mm_s', 'power_kw', 'is_anomalous'])
        
        current_time = start_time
        
        for _ in range(num_rows):
            temp = random.gauss(85.0, 2.0)
            pressure = random.gauss(120.0, 5.0)
            vibration = random.gauss(4.5, 0.5)
            power = random.gauss(450.0, 15.0)
            is_anomalous = 0
            
            if inject_anomaly:
                is_anomalous = 1
                power *= random.uniform(1.2, 1.4)      # 20-40% increase
                vibration *= random.uniform(1.3, 1.6)  # 30-60% increase
            
            writer.writerow([
                current_time.strftime('%Y-%m-%d %H:%M:%S'),
                'K-101',
                round(temp, 2),
                round(pressure, 2),
                round(vibration, 3),
                round(power, 2),
                is_anomalous
            ])
            
            current_time += timedelta(minutes=1)
            
    print(f"Success! Generated {num_rows} rows and saved to {file_path}")

if __name__ == "__main__":
    # Runs exactly 250 rows. Flip inject_anomaly to True for a failure day.
    generate_compressor_data(num_rows=250, inject_anomaly=False)