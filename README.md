# IPsecGuard AI

> **AI-Powered IPsec VPN Protocol Analyzer & Security Assessment Framework**  
> *Developed for the Smart India Hackathon (SIH) Prototype Demonstration (Problem Statement 160)*

![Version](https://img.shields.io/badge/Version-1.0.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-lightgrey.svg)
![Security-Standard](https://img.shields.io/badge/Standards-NIST%20SP%20800--77%20%7C%20RFC%204301-orange.svg)

---

## Executive Overview

**IPsecGuard AI** is an enterprise-grade defensive protocol analyzer and automated security assessment framework for IPsec VPNs. It provides cybersecurity operations center (SOC) analysts and network security engineers with instant visibility into cryptographic configurations, packet capture traces, and security association (SA) states.

The platform combines a **dual-engine architecture**:
1. **AI-Assisted Protocol Classification Engine**: Derives explainable confidence scores for encrypted payload traffic (e.g., VoIP vs. File Transfer) using Random Forest classification and SHAP (SHapley Additive exPlanations) values. It explicitly segregates empirically **DETECTED** metrics from heuristic **INFERRED** attributes to prevent hallucinated conclusions.
2. **Mathematical Security Assessment Engine**: Employs a 100-point deduction model rooted in **NIST SP 800-77 Rev. 1**, **RFC 4301**, **RFC 7296 (IKEv2)**, and **RFC 8221** to quantify security postures into LOW, MEDIUM, HIGH, and CRITICAL risk tiers with prioritized remediations.

---

## Architecture Diagram

The system operates strictly locally with no external APIs or cloud dependencies, ensuring complete data privacy for sensitive packet captures.

```mermaid
graph TD
    %% User Inputs
    subgraph Input Phase
        PCAP[PCAP / PCAPNG File] --> UploadAPI[FastAPI Upload Endpoint]
    end

    %% Backend Processing
    subgraph Backend Engine (Python / FastAPI)
        UploadAPI --> IKEParser[IKE/ESP Protocol Parser]
        IKEParser --> |Extracts Key Exchange Data| ComplianceEngine[Compliance & Scoring Engine]
        IKEParser --> |Extracts Packet Flow Shapes| FeatureExtractor[SPLT Feature Extractor]
        
        FeatureExtractor --> |Flow Statistics| MLModel[Random Forest Classifier]
        MLModel --> |Classification Output| SHAP[SHAP Tree Explainer]
        
        ComplianceEngine --> ThreatMatrix[Threat Matrix Generator]
    end

    %% Export & Reporting
    subgraph Reporting & Output
        ComplianceEngine --> JSONResponse[JSON API Response]
        SHAP --> JSONResponse
        ThreatMatrix --> JSONResponse
        
        JSONResponse --> PDFGen[PDF Report Generator]
        JSONResponse --> UIRender[HTML Dashboard UI]
        JSONResponse --> SIEM[SIEM / Syslog Emitter]
    end
```

---

## Workflow: How It Works

1. **Upload & Parse**: The user uploads a network capture (`.pcap` / `.pcapng`). The pure-Python packet parser (`parser/ike_parser.py`) extracts IKE negotiations (Phase 1 & Phase 2) and separates the encrypted ESP flows.
2. **Deterministic Compliance Scoring**: The parameters negotiated in the clear (e.g., AES-256-GCM, DH Group 14) are evaluated against a strict rule engine. Deductions are applied based on known cryptographic weaknesses (e.g., lack of PFS, MD5 usage).
3. **AI Traffic Classification**: The encrypted ESP packets are passed to the `ml_pipeline`. Flow characteristics (Sequence of Packet Lengths and Times - SPLT) are analyzed to infer the *type* of traffic inside the tunnel (e.g., VoIP, Video, Email, File Transfer) without decrypting the payload.
4. **Explainable AI (SHAP)**: The Random Forest model's decisions are passed through a SHAP Explainer. This generates live feature-importance values, telling the analyst *exactly* why the AI classified the traffic the way it did (e.g., "High packet rate and small packet size indicates VoIP").
5. **Reporting & Alerting**: The system generates a comprehensive UI dashboard, emits Syslog/CEF alerts for SIEM integration, and allows the user to download a dynamically generated, professional PDF report (Executive or Technical).

---

## Key Features for Judges

| Feature | Description | Architecture Component |
| :--- | :--- | :--- |
| **1. Zero Paid APIs** | Fully local explainable heuristic AI and RFC rule engine. No OpenAI, AWS, or cloud bills. | `backend/main.py`, `ml_pipeline/` |
| **2. Not Just a Mockup** | Real mathematical scoring, actual binary PCAP parsing, dynamic comparison, and live PDF report generation. | `backend/main.py`, `parser/ike_parser.py` |
| **3. Live SHAP Explanations** | The AI doesn't just guess; it provides dynamic, mathematical SHAP (SHapley Additive exPlanations) values to prove its reasoning to SOC analysts. | `backend/main.py`, `frontend/index.html` |
| **4. Detected vs Inferred** | Clearly tags each parameter and explains evidence to prevent security hallucinations. Cleartext = Detected. Encrypted traffic patterns = Inferred. | `backend/main.py`, `index.html` |
| **5. Interactive Threat Matrix** | Dynamic attack vector matrix mapping findings to severity, likelihood, impact, and mitigation status. | `index.html`, `backend/main.py` |
| **6. Demo & Live Modes** | Supports live `.pcap` uploads with a pure Python binary parser, as well as demo captured datasets. | `data/` |
| **7. Downloadable PDF Reports** | Generates standalone, self-contained PDF audit reports dynamically using `fpdf2`. | `backend/report_generator.py` |

---

## Project Structure

```text
IPsecGuard-AI/
├── backend/
│   ├── main.py                  # FastAPI server, compliance scoring & API endpoints
│   ├── report_generator.py      # Executive & technical PDF report engine using fpdf2
│   ├── syslog_emitter.py        # SIEM integration for sending CEF alerts
│   └── requirements.txt         # Python backend dependencies
│
├── frontend/
│   └── index.html               # Single-page HTML/CSS/JS dashboard UI
│
├── ml_pipeline/
│   ├── extract_features.py      # Extracts SPLT features from PCAPs
│   ├── train_model.py           # Trains the Random Forest classifier
│   └── random_forest_model.pkl  # Compiled model payload
│
├── parser/
│   └── ike_parser.py            # Custom pure-Python IKE/ESP binary PCAP parser
│
├── testbed/
│   ├── docker-compose.yml       # Virtual network simulation for data generation
│   └── scripts/                 # Automated traffic generators (iperf3, etc.)
│
├── docs/                        # Architecture decisions, pitch decks, research logs
└── data/                        # Demo PCAP files
```

---

## Getting Started

### 1. Installation

**Prerequisites:** Python 3.10+

```bash
git clone https://github.com/LuckyAnsari22/26160.git
cd 26160
pip install -r requirements.txt
```

### 2. Running the System

Start the backend API server:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

Open the frontend dashboard in your browser:
```bash
# Simply open frontend/index.html in any modern web browser
# Example on Windows:
start ../frontend/index.html
```

### 3. Usage
1. Open the dashboard.
2. Click **"Run Analysis"** on a demo capture OR use the **"Upload Capture"** tab to upload your own `.pcap` file.
3. Review the **Compliance Engine** tab for NIST/RFC rule grading.
4. Review the **SOC Analyst** tab for live AI traffic classification and SHAP explainability charts.
5. Review the **Threat Matrix** tab for actionable remediation steps.
6. Click **"Download Technical Report"** to export the dynamic PDF audit.

---

## Real Analysis vs. Simulated/Demo Features

In the spirit of complete transparency for the hackathon judging panel, here is exactly what is running live code versus what relies on synthetic models:

### 100% Live & Executed Locally:
- **PCAP Binary Parsing**: The `ike_parser.py` reads real bytes from uploaded `.pcap` files using `scapy`.
- **Compliance Scoring Engine**: The 100-point deduction system mathematically grades the actual parameters found in the upload.
- **Threat Matrix Generation**: Risk factors are mapped dynamically based on the exact rule violations found in the capture.
- **PDF Generation**: The `/export` endpoint dynamically constructs real PDF reports using the `fpdf2` library, injecting live data—nothing is hardcoded.
- **SHAP Explanation**: The backend actively unpacks the `CalibratedClassifierCV` wrapper to compute live SHAP values via `TreeExplainer` on the exact packet flow statistics being analyzed.

### Inferred / Model-Based Features:
- **Payload Traffic Classification**: Because ESP payloads are cryptographically secure, the exact traffic type cannot be deterministically proven. We use a Random Forest model trained on SPLT (Sequence of Packet Lengths and Times) to infer the traffic class. The model was trained on synthetic data crafted to mimic standard distributions (e.g., bursty email traffic via `iperf3`, continuous video streams).

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.
