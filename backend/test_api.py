import requests
import time
import json
import os

API_URL = "http://localhost:8000/api/v1"

def test_pipeline():
    print("1. Creating dummy pcap file...")
    with open("dummy.pcap", "wb") as f:
        f.write(b"dummy data")

    print("\n2. Submitting to FastAPI backend...")
    with open("dummy.pcap", "rb") as f:
        res = requests.post(f"{API_URL}/analyze", files={"file": f})
    
    if res.status_code != 200:
        print("API failed:", res.text)
        return
        
    data = res.json()
    analysis_id = data["analysis_id"]
    print(f" -> Success. Analysis ID: {analysis_id}")
    
    print("\n3. Waiting for processing...")
    time.sleep(1)
    
    print("\n4. Fetching results...")
    res = requests.get(f"{API_URL}/results/{analysis_id}")
    results = res.json()
    
    print(" -> Compliance Score:", results["compliance"]["score"])
    print(" -> Predicted Class:", results["classification"]["predicted_class"])
    print(" -> Confidence:", results["classification"]["confidence"])
    print(" -> Countermeasure Overhead:", results["countermeasures"]["adaptive_overhead_pct"])
    
    print("\n5. Checking Syslog JSON emitter...")
    if os.path.exists("logs/siem_syslog.jsonl"):
        with open("logs/siem_syslog.jsonl", "r") as f:
            lines = f.readlines()
            print(" -> Emitted Alerts:")
            for line in lines:
                log_obj = json.loads(line)
                print(f"    [{log_obj['event_type']}] {log_obj['message']}")

if __name__ == "__main__":
    test_pipeline()
