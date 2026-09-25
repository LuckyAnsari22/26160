import time
import requests
import subprocess
import os

API_URL = "http://localhost:8000/api/v1"

def run_e2e_test():
    print("==========================================")
    print("STARTING E2E PIPELINE TEST")
    print("==========================================")
    start_time = time.time()
    
    # 1. Pcap simulation
    t0 = time.time()
    with open("dummy.pcap", "wb") as f:
        f.write(b"dummy")
    print(f"1. PCAP generated: {time.time()-t0:.2f}s")
    
    # 2. Upload to backend
    t0 = time.time()
    try:
        with open("dummy.pcap", "rb") as f:
            res = requests.post(f"{API_URL}/analyze", files={"file": f})
        data = res.json()
        analysis_id = data["analysis_id"]
        print(f"2. Backend upload & processing initiated: {time.time()-t0:.2f}s")
    except Exception as e:
        print(f"Backend failed! Is main.py running? Error: {e}")
        return
        
    # 3. Wait for mocked extraction and inference
    t0 = time.time()
    while True:
        res = requests.get(f"{API_URL}/results/{analysis_id}")
        if res.status_code == 200 and res.json().get("status") == "completed":
            break
        time.sleep(0.1)
    
    result = res.json()
    print(f"3. Parser -> Classifier -> Countermeasure pipeline finished: {time.time()-t0:.2f}s")
    print(f"   -> Found Class: {result['classification']['predicted_class']}")
    print(f"   -> Overhead Calculated: {result['countermeasures']['adaptive_overhead_pct']}%")
    
    # 4. Generate Reports
    t0 = time.time()
    subprocess.run(["python", "backend/report_generator.py"], capture_output=True)
    print(f"4. PDF Reports generated: {time.time()-t0:.2f}s")
    
    total_time = time.time() - start_time
    print("==========================================")
    print(f"E2E PIPELINE SUCCESS - TOTAL TIME: {total_time:.2f}s")
    print("==========================================")

if __name__ == "__main__":
    run_e2e_test()
