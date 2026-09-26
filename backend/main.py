import os
import uuid
import logging
import traceback
from fastapi import FastAPI, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Relative imports assuming execution from root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.syslog_emitter import emit_alert

# Scapy is a hard dependency of the real pipeline (IKEParser, SPLTFeatureExtractor).
# Imported at module level, NOT inside a try/except: if it's missing, the server
# must fail loudly at startup, not start successfully and silently return
# "indeterminate" for every request (which would be indistinguishable from a
# genuinely sparse capture and would hide an environment problem as a data problem).
from scapy.all import rdpcap, ISAKMP, ESP, UDP

import joblib
import pandas as pd
import numpy as np

from parser.ike_parser import IKEParser
from parser.rule_engine import SecurityRuleEngine
from ml_pipeline.feature_extractor import SPLTFeatureExtractor
from ml_pipeline.adversarial_padding import apply_mtu_padding, apply_adaptive_padding
from backend.report_generator import generate_executive_report, generate_technical_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI-Powered IPsec Analyzer API", version="1.0")

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")
MODEL_PATH = os.path.join(BASE_DIR, "models", "calibrated_rf_model.pkl")
MODE_MODEL_PATH = os.path.join(BASE_DIR, "models", "mode_classifier.pkl")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# These are the exact 8 columns train_model.py fit the model on
# (df.drop(columns=["flow_id", "config", "label", "max_len", "min_len"])).
# Selected explicitly here rather than relying on drop() so column order is
# guaranteed to match what the model was trained on regardless of dict ordering.
FEATURE_COLS = [
    "pkt_count", "direction_ratio", "mean_len", "std_len",
    "mean_iat", "std_iat", "max_iat", "flow_duration",
]

# Loaded once at startup, not per-request. If the model file is missing/corrupt,
# fail loudly now rather than returning fake classifications later.
ML_MODEL = None
if os.path.exists(MODEL_PATH):
    ML_MODEL = joblib.load(MODEL_PATH)
    logger.info(f"Loaded ML model from {MODEL_PATH}")
else:
    logger.warning(f"No model file found at {MODEL_PATH} - classification will report 'unavailable'.")

# Separate model from the traffic-type classifier above - see
# train_mode_classifier.py's docstring for why this is its own pipeline.
# Tunnel-vs-Transport mode is never observable in cleartext (ike_parser.py
# correctly reports "UNKNOWN" for it), but Tunnel mode ESP-encrypts the
# entire original IP packet while Transport mode does not, so the ESP
# ciphertext is structurally ~20-40 bytes larger in Tunnel mode (inner IPv4/
# IPv6 header size), modulo cipher padding and MTU effects. Verified against
# this project's real testbed captures via leave-one-variant-out
# cross-validation: balanced accuracy ~0.55 (close to chance/0.50) at the
# available sample size (8 variants: 6 tunnel, 2 transport) - reported
# honestly as unreliable below, not dressed up as a working classifier.
MODE_MODEL = None
MODE_MODEL_FEATURES = None
MODE_MODEL_LOGO_BALANCED_ACCURACY = 0.55
if os.path.exists(MODE_MODEL_PATH):
    _mode_bundle = joblib.load(MODE_MODEL_PATH)
    MODE_MODEL = _mode_bundle["model"]
    MODE_MODEL_FEATURES = _mode_bundle["features"]
    logger.info(f"Loaded mode classifier from {MODE_MODEL_PATH} (features: {MODE_MODEL_FEATURES})")
else:
    logger.warning(f"No mode classifier found at {MODE_MODEL_PATH} - mode inference will report 'unavailable'.")

# In-memory store for demo purposes
analysis_results = {}


@app.post("/api/v1/analyze")
async def analyze_pcap(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Accepts a PCAP, persists it to disk, and kicks off real asynchronous analysis."""
    analysis_id = str(uuid.uuid4())

    contents = await file.read()
    safe_name = os.path.basename(file.filename or "upload.pcap")
    save_path = os.path.join(UPLOAD_DIR, f"{analysis_id}_{safe_name}")
    with open(save_path, "wb") as f:
        f.write(contents)

    analysis_results[analysis_id] = {"status": "processing", "filename": safe_name}
    background_tasks.add_task(process_pcap, analysis_id, safe_name, save_path)

    return {"analysis_id": analysis_id, "status": "processing"}


def _inspect_pcap(filepath: str):
    """
    Reads the pcap once to validate it and get ground-truth IKE/ESP packet counts,
    independent of what the two engines individually find. This is what lets us
    tell "not a real pcap" apart from "a real pcap with no IKE handshake in it" -
    two very different failure modes that must not be reported identically.
    Also tracks whether a CREATE_CHILD_SA exchange (IKEv2 exchange type 36)
    was observed - this is the ONLY way PFS status is ever visible on the
    wire (a CHILD_SA rekey with a fresh KE payload), and even then only its
    existence is visible in cleartext, not its contents (the exchange itself
    is encrypted). Without one, PFS is not "disabled", it's unknown, and the
    rule engine's default-to-disabled assumption must not be presented as a
    confirmed finding in that case.

    Also extracts per-SPI ESP sequence numbers for the replay readiness check.
    Per RFC 4303 Section 2, ESP SPI and Sequence Number fields are NOT
    encrypted - they are cleartext header fields the receiver needs to look
    up the SA and check the anti-replay window BEFORE decryption.

    Raises on a genuinely invalid capture file.
    """
    from collections import defaultdict

    packets = rdpcap(filepath)
    total = len(packets)
    ike_count = 0
    esp_count = 0
    saw_create_child_sa = False
    esp_seq_by_spi = defaultdict(list)
    for pkt in packets:
        if ESP in pkt:
            esp_count += 1
            # Extract cleartext SPI and sequence number (RFC 4303 §2:
            # these are NOT encrypted, they precede the encrypted payload)
            spi = pkt[ESP].spi
            seq = pkt[ESP].seq
            esp_seq_by_spi[spi].append(seq)
        elif UDP in pkt and pkt[UDP].dport in (500, 4500):
            ike_count += 1
            if ISAKMP in pkt and pkt[ISAKMP].exch_type == 36:
                saw_create_child_sa = True
        elif ISAKMP in pkt:
            ike_count += 1
            if pkt[ISAKMP].exch_type == 36:
                saw_create_child_sa = True
    # Convert SPI keys to hex strings for JSON serialization and readability
    esp_seq_by_spi_str = {f"0x{spi:08x}": seqs for spi, seqs in esp_seq_by_spi.items()}
    return total, ike_count, esp_count, saw_create_child_sa, esp_seq_by_spi_str


def _classify_and_simulate(flow: dict) -> dict:
    """Runs the real trained model + the real countermeasure simulator on one flow."""
    row = pd.DataFrame([flow])
    X = row[FEATURE_COLS]

    pred = ML_MODEL.predict(X)[0]
    proba = ML_MODEL.predict_proba(X)[0]
    confidence = float(np.max(proba)) * 100

    mtu_df, mtu_overhead = apply_mtu_padding(row.copy())
    mtu_confidence = float(np.max(ML_MODEL.predict_proba(mtu_df[FEATURE_COLS])[0])) * 100

    adaptive_df, adaptive_overhead = apply_adaptive_padding(row.copy(), target_overhead=0.3)
    adaptive_confidence = float(np.max(ML_MODEL.predict_proba(adaptive_df[FEATURE_COLS])[0])) * 100

    shap_explanation = None
    try:
        import shap
        try:
            base_estimator = ML_MODEL.estimator
        except AttributeError:
            base_estimator = ML_MODEL.estimators_[0].estimator
            
        explainer = shap.TreeExplainer(base_estimator)
        shap_values = explainer.shap_values(X)
        
        class_idx = np.where(ML_MODEL.classes_ == pred)[0][0]
        if isinstance(shap_values, list):
            sv = shap_values[class_idx][0]
        elif len(shap_values.shape) == 3:
            sv = shap_values[0, :, class_idx]
        else:
            sv = shap_values[0]
            
        expected_val = explainer.expected_value
        if isinstance(expected_val, list) or isinstance(expected_val, np.ndarray):
            expected_val = expected_val[class_idx]
            
        top_features = []
        for i, col in enumerate(FEATURE_COLS):
            top_features.append({
                "feature": col,
                "shap_value": float(sv[i]),
                "actual_value": float(X.iloc[0][i])
            })
            
        top_features.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
        
        shap_explanation = {
            "base_value": float(expected_val),
            "top_features": top_features,
            "predicted_class": str(pred)
        }
    except Exception as e:
        logger.error(f"SHAP computation failed: {e}")
        shap_explanation = None

    return {
        "status": "classified",
        "predicted_class": str(pred),
        "confidence": round(confidence, 1),
        "flow_stats": {
            "pkt_count": flow["pkt_count"],
            "mean_len": flow["mean_len"],
            "mean_iat": flow["mean_iat"],
            "direction_ratio": flow["direction_ratio"],
        },
        "countermeasures": {
            "mtu_overhead_pct": round(mtu_overhead * 100, 2),
            "mtu_confidence": round(mtu_confidence, 1),
            "adaptive_overhead_pct": round(adaptive_overhead * 100, 2),
            "adaptive_confidence": round(adaptive_confidence, 1),
        },
        "shap_explanation": shap_explanation,
    }


def _infer_mode(flow: dict) -> dict:
    """
    Statistically infers Tunnel vs Transport mode from the ESP payload-length
    structural signal (see train_mode_classifier.py's docstring for the full
    physical rationale and evaluation methodology).

    IMPORTANT, deliberately distinct from _classify_and_simulate() above:
    encryption/PRF/DH-group come from cleartext IKE fields (ike_parser.py) -
    those are protocol extraction, not inference, and are reliable by
    construction. Mode is never in cleartext at all (ike_parser.py correctly
    reports "UNKNOWN" for it - that is not a bug, see its docstring). This
    function instead does a real statistical inference from ciphertext
    length, evaluated honestly at ~0.55 balanced accuracy (chance is 0.50)
    via leave-one-variant-out cross-validation on this project's own real
    testbed captures - not reliable enough to present with a calibrated
    confidence the way the traffic classifier's is. The raw prediction is
    still returned (this was genuinely attempted end-to-end, not skipped),
    but callers must surface `reliability`/`validated_balanced_accuracy`
    alongside it, never `predicted_mode` alone.
    """
    if MODE_MODEL is None:
        return {"status": "unavailable", "reason": "No mode classifier file found on disk."}

    esp_mean_len = flow.get("esp_mean_len")
    if esp_mean_len is None or (isinstance(esp_mean_len, float) and np.isnan(esp_mean_len)):
        return {
            "status": "indeterminate",
            "reason": "This flow contains no ESP packets (e.g. an IKE-only capture) - "
                      "the ESP payload-length signal this inference depends on doesn't exist here.",
        }

    row = pd.DataFrame([flow])
    X = row[MODE_MODEL_FEATURES]
    pred = MODE_MODEL.predict(X)[0]

    return {
        "status": "inferred",
        "predicted_mode": str(pred),
        "method": (
            "Statistical inference from ESP ciphertext payload length, NOT extracted "
            "from a plaintext protocol field. Tunnel mode ESP-encrypts the entire "
            "original IP packet (own IP header included); Transport mode does not - "
            "so the ESP ciphertext is structurally larger in Tunnel mode by roughly "
            "the inner IP header size (~20 bytes IPv4 / ~40 bytes IPv6), modulo cipher "
            "block-padding and MTU/segmentation effects."
        ),
        "reliability": "LOW",
        "reliability_note": (
            "Leave-one-variant-out cross-validation on this project's real testbed "
            "captures (8 variants: 6 tunnel, 2 transport) gives balanced accuracy of "
            f"~{MODE_MODEL_LOGO_BALANCED_ACCURACY:.2f} - close to chance level (0.50). "
            "This prediction should NOT be treated as reliable; more real captures "
            "across more cipher/mode combinations would be needed to validate it "
            "further. Reported for transparency about what was attempted, not as a "
            "validated result."
        ),
        "validated_balanced_accuracy": MODE_MODEL_LOGO_BALANCED_ACCURACY,
    }


def process_pcap(analysis_id: str, filename: str, filepath: str):
    """
    Real processing pipeline: parses the actual uploaded pcap through the
    deterministic IKE parser + rule engine, the real SPLT feature extractor +
    trained classifier, and the real countermeasure simulator. Every field in
    the result is either a genuinely computed value or an explicit
    indeterminate/error status - there is no hardcoded fallback data.
    """
    try:
        total_packets, ike_packets, esp_packets, saw_create_child_sa, esp_seq_by_spi = _inspect_pcap(filepath)
    except Exception as e:
        logger.warning(f"[{analysis_id}] Invalid pcap '{filename}': {e}")
        analysis_results[analysis_id] = {
            "status": "error",
            "filename": filename,
            "error": f"Not a valid pcap file: {e}",
        }
        return

    if total_packets == 0:
        analysis_results[analysis_id] = {
            "status": "error",
            "filename": filename,
            "error": "Pcap parsed successfully but contains zero packets.",
        }
        return

    try:
        # --- Tier 1: Deterministic IKE parsing ---
        parsed = IKEParser(filepath).parse()

        ike_observed = (
            parsed["ike_version"] != "UNKNOWN"
            or bool(parsed["encryption_algorithm"])
            or bool(parsed["dh_group"])
        )

        # --- Tier 2: Real SPLT feature extraction + classification ---
        # Runs BEFORE the rule engine because the rule engine now scores
        # metadata exposure from the classifier's confidence (if available).
        # These are independent pipelines: classification does not depend on
        # compliance or vice versa — they both feed INTO the rule engine.
        classifier_confidence = None
        if esp_packets == 0:
            classification_section = {
                "status": "indeterminate",
                "reason": f"No ESP traffic observed in capture ({total_packets} total packets).",
            }
            mode_inference_section = {
                "status": "indeterminate",
                "reason": f"No ESP traffic observed in capture ({total_packets} total packets).",
            }
        else:
            extractor = SPLTFeatureExtractor(filepath, label="unknown", config="live-upload")
            extractor.extract_raw_flows()
            flows = extractor.compute_features()

            if not flows:
                classification_section = {
                    "status": "indeterminate",
                    "reason": (
                        f"{esp_packets} ESP packets observed, but no flow met the "
                        "20-packet minimum required for reliable classification."
                    ),
                }
                mode_inference_section = {
                    "status": "indeterminate",
                    "reason": (
                        f"{esp_packets} ESP packets observed, but no flow met the "
                        "20-packet minimum required for reliable classification."
                    ),
                }
            else:
                # Normally exactly one flow for a single client-to-gateway
                # tunnel (feature_extractor.py keys flows by outer IP pair
                # only, fixed this session - see its own docstring for the
                # SPI-splitting bug that used to cause 2 flows here). More
                # than one is still possible (e.g. a mid-capture rekey using
                # a fresh SPI pair on the same IPs), so report the largest
                # and surface the true count rather than silently picking one.
                top_flow = max(flows, key=lambda f: f["pkt_count"])
                mode_inference_section = _infer_mode(top_flow)

                if ML_MODEL is None:
                    classification_section = {
                        "status": "unavailable",
                        "reason": "No trained model file found on disk.",
                    }
                else:
                    classification_section = _classify_and_simulate(top_flow)
                    classification_section["total_flows_detected"] = len(flows)
                    classifier_confidence = classification_section.get("confidence")

        # --- Inject data for the rule engine's new assessments ---
        # esp_seq_by_spi: per-SPI ESP sequence numbers for replay readiness
        # (extracted from cleartext ESP headers by _inspect_pcap)
        parsed["esp_seq_by_spi"] = esp_seq_by_spi
        # classifier_confidence: for metadata exposure scoring (None if
        # classifier did not run — rule engine handles this as indeterminate)
        parsed["classifier_confidence"] = classifier_confidence

        # --- Rule engine: scores IKE params + replay readiness + metadata exposure ---
        rule_result = SecurityRuleEngine(parsed).evaluate()

        if ike_packets == 0 or not ike_observed:
            compliance_section = {
                "status": "indeterminate",
                "reason": (
                    f"No IKE_SA_INIT/IKE_AUTH packets observed in this capture "
                    f"({total_packets} total packets, {esp_packets} ESP). "
                    "Cryptographic compliance cannot be assessed from ESP-only "
                    "traffic - the IKE handshake must be present in the capture."
                ),
                "raw_parameters": parsed,
                "key_lifetime_status": rule_result["key_lifetime_status"],
                "replay_readiness": rule_result["replay_readiness"],
                "metadata_exposure": rule_result["metadata_exposure"],
            }
        else:
            # PFS is only ever visible on the wire as a CREATE_CHILD_SA rekey
            # exchange existing at all (its contents are still encrypted).
            # Verified against a real capture: rule_engine.py has no way to
            # distinguish "confirmed disabled" from "never rekeyed during
            # this capture" and defaults unknown to disabled, which produced
            # a HIGH-severity "PFS disabled" finding on a variant whose own
            # config name is tunnel-aes256gcm-ecp256-pfs. Rather than touch
            # rule_engine.py's trusted, tested logic, strip that specific
            # finding here and recompute the score without it when we know
            # it's a visibility limitation, not a real finding.
            pfs_finding_text = (
                "Perfect Forward Secrecy (PFS) is disabled. Compromise of "
                "IKE keys compromises all past ESP traffic."
            )
            pfs_caveat = None
            if not parsed["pfs"] and not saw_create_child_sa:
                findings = [f for f in rule_result["findings"] if f["message"] != pfs_finding_text]
                threat_matrix = [t for t in rule_result["threat_matrix"] if t != pfs_finding_text]
                score = min([f["cap_applied"] for f in findings], default=100)
                pfs_caveat = (
                    "PFS status could not be determined: no CREATE_CHILD_SA "
                    "rekey was observed in this capture. PFS is only "
                    "observable during a rekey, which is rare in a short "
                    "capture and encrypted regardless - this is a capture "
                    "visibility limit, not a confirmed misconfiguration."
                )
            else:
                findings = rule_result["findings"]
                threat_matrix = rule_result["threat_matrix"]
                score = rule_result["security_score"]

            compliance_section = {
                "status": "assessed",
                "score": score,
                "risk_score": 100 - score,
                "findings": findings,
                "threat_matrix": threat_matrix,
                "raw_parameters": parsed,
                "key_lifetime_status": rule_result["key_lifetime_status"],
                "replay_readiness": rule_result["replay_readiness"],
                "metadata_exposure": rule_result["metadata_exposure"],
            }
            if pfs_caveat:
                compliance_section["caveats"] = [pfs_caveat]

        result = {
            "status": "completed",
            "filename": filename,
            "capture_summary": {
                "total_packets": total_packets,
                "ike_packets": ike_packets,
                "esp_packets": esp_packets,
            },
            "compliance": compliance_section,
            "classification": classification_section,
            "mode_inference": mode_inference_section,
        }
        analysis_results[analysis_id] = result

        # Emit SIEM alerts only for genuinely assessed findings - never for
        # indeterminate/error results, since there is nothing real to alert on.
        if compliance_section["status"] == "assessed" and compliance_section["threat_matrix"]:
            emit_alert(
                message=f"Compliance findings in {filename}: {'; '.join(compliance_section['threat_matrix'])}",
                event_type="compliance_violation",
                severity=100 - compliance_section["score"],
                flow_id=filename,
                mitre_tactics=["TA0006 Credential Access"],
                mitre_techniques=["T1552 Unsecured Credentials"],
            )
        if classification_section.get("status") == "classified" and classification_section["confidence"] > 90:
            emit_alert(
                message=f"High-confidence {classification_section['predicted_class']} traffic classified in {filename}",
                event_type="traffic_classification",
                severity=10,
                flow_id=filename,
                mitre_tactics=["TA0011 Command and Control"],
                mitre_techniques=["T1573 Encrypted Channel"],
            )

    except Exception as e:
        # A real, unexpected failure (e.g. ike_parser.py or feature_extractor.py
        # breaking against real-world traffic shapes it wasn't tested against)
        # must surface as a visible error, not silently fall back to fake data.
        logger.error(f"[{analysis_id}] Pipeline failure on '{filename}': {e}")
        logger.error(traceback.format_exc())
        analysis_results[analysis_id] = {
            "status": "error",
            "filename": filename,
            "error": f"{type(e).__name__}: {e}",
        }


@app.get("/api/v1/results/{analysis_id}")
async def get_results(analysis_id: str):
    """Returns the full parsed results for the 3 personas."""
    res = analysis_results.get(analysis_id)
    if not res:
        return JSONResponse(status_code=404, content={"error": "Analysis ID not found"})
    return res


@app.get("/api/v1/assets/{image_name}")
async def get_asset(image_name: str):
    """Serves the generated SHAP and Countermeasure charts."""
    file_path = os.path.join(os.path.dirname(__file__), "..", "docs", "assets", image_name)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return JSONResponse(status_code=404, content={"error": "Asset not found"})


@app.get("/api/v1/export/{analysis_id}")
async def export_report(analysis_id: str, report_type: str = "executive"):
    """
    Generates and returns a real PDF file rendered from the actual analysis
    results for this analysis_id. Both report types (executive/technical)
    receive the full result dict and render every field dynamically — there
    are no hardcoded values in the generated PDF.
    """
    res = analysis_results.get(analysis_id)
    if not res:
        return JSONResponse(status_code=404, content={"error": "Analysis ID not found"})

    try:
        if report_type == "technical":
            out_path = generate_technical_report(res)
        else:
            out_path = generate_executive_report(res)
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        return JSONResponse(status_code=500, content={"error": f"Report generation failed: {e}"})

    if not os.path.exists(out_path):
        return JSONResponse(status_code=500, content={"error": "Report generator did not produce a file"})

    return FileResponse(out_path, media_type="application/pdf", filename=os.path.basename(out_path))


# Mount frontend static files last so it doesn't shadow API routes
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "frontend"), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
