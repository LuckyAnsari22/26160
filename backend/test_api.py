import requests
import time
import json
import os
from pathlib import Path

API_URL = "http://localhost:8000/api/v1"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _submit_and_wait(filename, content, timeout=30):
    res = requests.post(f"{API_URL}/analyze", files={"file": (filename, content)})
    assert res.status_code == 200, f"API failed: {res.text}"
    analysis_id = res.json()["analysis_id"]
    print(f" -> Submitted. Analysis ID: {analysis_id}")

    deadline = time.time() + timeout
    while True:
        results = requests.get(f"{API_URL}/results/{analysis_id}").json()
        if results.get("status") != "processing" or time.time() > deadline:
            return results
        time.sleep(0.5)


def test_pipeline():
    pcap = FIXTURES_DIR / "real_ike_sa_init_aes256gcm_ecp256.pcap"
    print(f"1. Submitting real fixture {pcap.name} to FastAPI backend...")
    results = _submit_and_wait(pcap.name, pcap.read_bytes())

    assert results["status"] == "completed", results
    assert results["compliance"]["status"] == "assessed"
    score = results["compliance"]["score"]
    assert isinstance(score, int) and 0 <= score <= 100
    print(" -> Compliance Score:", score)

    # Handshake-focused capture: far fewer ESP packets than the 20-packet
    # classification minimum, so the classifier must report indeterminate
    # rather than invent a prediction.
    assert results["capture_summary"]["esp_packets"] < 20
    assert results["classification"]["status"] == "indeterminate"
    print(" -> Classification:", results["classification"]["reason"])

    print("\n2. Checking Syslog JSON emitter...")
    if os.path.exists("logs/siem_syslog.jsonl"):
        with open("logs/siem_syslog.jsonl", "r") as f:
            lines = f.readlines()
            print(" -> Emitted Alerts:")
            for line in lines:
                log_obj = json.loads(line)
                print(f"    [{log_obj['event_type']}] {log_obj['message']}")


def test_pipeline_rejects_invalid_pcap():
    print("1. Submitting garbage bytes as a pcap...")
    results = _submit_and_wait("dummy.pcap", b"dummy data")

    assert results["status"] == "error", results
    assert "compliance" not in results
    print(" -> Rejected:", results["error"])


if __name__ == "__main__":
    test_pipeline()
    test_pipeline_rejects_invalid_pcap()
