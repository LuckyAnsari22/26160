# Prompts to Complete Remaining Gaps

---

## Prompt 1: `report_generator.py` — Dynamic PDF from Real Analysis Data

> **Context**: I have a FastAPI backend at `backend/main.py` that analyzes IPsec pcap files. The endpoint `POST /api/v1/analyze` triggers `process_pcap()` which produces a result dict stored in-memory at `analysis_results[analysis_id]`. The endpoint `GET /api/v1/export/{analysis_id}?report_type=executive|technical` calls `backend/report_generator.py` and returns a PDF.
>
> **Current problem**: `report_generator.py` has two functions — `generate_executive_report()` and `generate_technical_report()` — that take **zero arguments** and write hardcoded static text into a PDF using `fpdf2`. The PDF content is always identical regardless of what was actually analyzed. The `/export` endpoint calls them but doesn't pass the analysis data.
>
> **The exact JSON schema `process_pcap()` produces** (this is what the report must render):
> ```python
> {
>     "status": "completed" | "error",
>     "filename": "upload.pcap",
>     "capture_summary": {
>         "total_packets": int,
>         "ike_packets": int,
>         "esp_packets": int
>     },
>     "compliance": {
>         "status": "assessed" | "indeterminate",
>         # When assessed:
>         "score": int,           # 0-100
>         "risk_score": int,      # 100-score
>         "findings": [{"severity": str, "message": str, "cap_applied": int}],
>         "threat_matrix": [str],
>         "key_lifetime_status": {"status": "not_assessable", "reason": str},
>         "replay_readiness": {"status": "assessed"|"indeterminate", "result": str, "severity": str, "message": str, "caveat": str},
>         "metadata_exposure": {"status": "assessed"|"indeterminate", "severity": str, "classifier_confidence": float, "message": str},
>         "raw_parameters": {
>             "ike_version": str,
>             "encryption_algorithm": [str],
>             "integrity_algorithm": [str],
>             "prf_algorithm": [str],
>             "dh_group": [str]
>         },
>         "caveats": [str]  # optional
>     },
>     "classification": {
>         "status": "classified" | "indeterminate" | "unavailable",
>         # When classified:
>         "predicted_class": str,
>         "confidence": float,
>         "flow_stats": {"pkt_count": int, "mean_len": float, "mean_iat": float, "direction_ratio": float},
>         "countermeasures": {
>             "mtu_overhead_pct": float,
>             "mtu_confidence": float,
>             "adaptive_overhead_pct": float,
>             "adaptive_confidence": float
>         }
>     },
>     "mode_inference": {
>         "status": "inferred" | "indeterminate" | "unavailable",
>         "predicted_mode": str,
>         "reliability": "LOW",
>         "validated_balanced_accuracy": float
>     }
> }
> ```
>
> **What I need you to build**:
>
> Rewrite `backend/report_generator.py` so both functions accept the full analysis result dict and render it into a professional PDF using `fpdf2`. Requirements:
>
> 1. **Executive Report**: 1-2 pages for a CISO. Must include:
>    - A prominent risk score gauge/display (score/100)
>    - A plain-English summary of the compliance status (what was found, what's critical)
>    - Traffic analysis resistance summary (metadata exposure severity + classifier confidence)
>    - A "Recommended Actions" section derived from actual findings (not hardcoded)
>    - Caveats section if any exist (PFS visibility, key lifetime not assessable, etc.)
>
> 2. **Technical Report**: 3-5 pages for a security engineer. Must include everything in the executive plus:
>    - Full parsed SA parameters table (IKE version, encryption, integrity, PRF, DH group)
>    - Every finding with its severity, message, and severity cap applied
>    - Replay readiness assessment with the RFC 4303 caveat
>    - Metadata exposure detail with classifier confidence and countermeasure overhead numbers
>    - Mode inference result with the honest reliability note
>    - Capture summary stats (total/IKE/ESP packet counts)
>
> 3. **Handle every status combination gracefully**: compliance can be `assessed` or `indeterminate`, classification can be `classified`/`indeterminate`/`unavailable`, mode can be `inferred`/`indeterminate`/`unavailable`. The report must render a sensible page for ALL of them (e.g., "Compliance could not be assessed: no IKE handshake in capture" when indeterminate), not crash or show blanks.
>
> 4. Also update `backend/main.py`'s `/api/v1/export/{analysis_id}` endpoint to pass the real `analysis_results[analysis_id]` dict to the report functions instead of calling them with no arguments.
>
> 5. Use color coding for severity: CRITICAL=red, HIGH=orange, MEDIUM=yellow, PASS=green. Give each report a header with "IPsecGuard AI — Security Assessment Report" and the filename + timestamp.
>
> 6. Do NOT use any external template files. Everything in pure Python + fpdf2. Preserve the existing file path conventions (reports written to `docs/reports/`).

---

## Prompt 2: ISCXVPN2016 Claim — Honest Relabeling Across All Documents

> **Context**: My project claims in multiple places that we achieved "99.44% generalization accuracy" by replaying the public ISCXVPN2016 dataset through our IPsec testbed. This is **not true** — the validation was actually run against synthetic data generated by `ml_pipeline/generate_iscx_features.py`, which fabricates rows using `np.random.normal` with hand-picked parameters, never touching any real PCAP. The script `testbed/scripts/replay_iscxvpn.sh` that would do the actual download+tcpreplay is a placeholder that was never executed (confirmed: `build_log.md` admits "Status: Script written. Awaiting execution environment").
>
> **What I need you to do**: Search every file in the project for mentions of ISCXVPN2016, the 99.44% number, "generalization validation", "external dataset", "tcpreplay validation", and any similar claims. For each one found:
>
> 1. **Relabel it honestly** — change "VALIDATED" tags to "SYNTHETIC/ILLUSTRATIVE", change "99.44% generalization accuracy on ISCXVPN2016" to something like "99.44% accuracy on synthetic data shaped to approximate ISCXVPN2016 distributions — real dataset replay not yet executed". Don't delete the content or the aspiration — just make every claim match what was actually done.
>
> 2. **Files to check** (at minimum, there may be more):
>    - `docs/build_log.md`
>    - `PS26160_FINAL_PPT_DECK.md`
>    - `docs/mbalevel0.md`
>    - `docs/tech.md`
>    - `docs/research_dossier.md`
>    - `docs/deplomentscalabilitypanelpitch.md`
>    - `ml_pipeline/generate_iscx_features.py` (add a docstring caveat)
>    - `testbed/scripts/replay_iscxvpn.sh` (add a header comment saying it was never executed)
>
> 3. **Add a new section to `docs/build_log.md`** titled "Honesty Note: ISCXVPN2016 Validation Status" that clearly states: the synthetic generation pipeline exists and produces plausible feature distributions, but real PCAP replay through the IPsec tunnel has not been completed. The 99.44% number validates synthetic-vs-synthetic consistency, not real-world generalization. Include what would be needed to actually do it (download the ~20GB dataset, tcprewrite to remap IPs, tcpreplay through the strongSwan testbed, re-extract features with the real `SPLTFeatureExtractor`).
>
> 4. **Tone**: Not apologetic, not defensive. Frame it the way an honest researcher would: "We built the infrastructure for external validation (tcpreplay pipeline, IP remapping script) but have not yet executed it against the real dataset. The synthetic approximation shows the model architecture generalizes across distribution shapes; real-world validation remains a planned next step." This is actually stronger than hiding it — a judge who discovers the gap themselves will penalize much harder than one who sees you disclosed it.
>
> Show me every file changed and the exact diff.

---

## Prompt 3: Live SHAP Explanations Wired into API

> **Context**: I have a trained Random Forest classifier wrapped in `CalibratedClassifierCV` (Platt scaling), saved as `models/calibrated_rf_model.pkl` (and `models/calibrated_rf_model_real.pkl` for the real-data version). It classifies encrypted IPsec traffic into types (icmp, voip, video, web, bulk, email) from 8 SPLT features: `pkt_count`, `direction_ratio`, `mean_len`, `std_len`, `mean_iat`, `std_iat`, `max_iat`, `flow_duration`.
>
> The model is loaded at startup in `backend/main.py` as `ML_MODEL`. Classification happens in `_classify_and_simulate(flow)` which already calls `ML_MODEL.predict(X)` and `ML_MODEL.predict_proba(X)`.
>
> **Current gap**: The frontend's SOC Analyst tab previously crashed reading `results.classification.shap_explanation.top_features` which doesn't exist in the API response. It was patched to show a static training-time SHAP image instead. I want to add real per-request SHAP values.
>
> **What I need you to build**:
>
> 1. In `backend/main.py`, add SHAP computation to `_classify_and_simulate()`. Use `shap.TreeExplainer` on the underlying `CalibratedClassifierCV` model. The tricky part: `CalibratedClassifierCV` wraps the base estimator — you need to access `ML_MODEL.estimators_[0].estimator` (or the equivalent path depending on sklearn version) to get the actual `RandomForestClassifier` that `TreeExplainer` can work with. Handle the case where this access path doesn't work (different sklearn version) gracefully — return `shap_explanation: null` rather than crashing.
>
> 2. Return SHAP values in the classification response as:
>    ```json
>    "shap_explanation": {
>        "base_value": float,
>        "top_features": [
>            {"feature": "mean_len", "shap_value": 0.23, "actual_value": 148.5},
>            {"feature": "mean_iat", "shap_value": -0.15, "actual_value": 0.021},
>            ...
>        ],
>        "predicted_class": "voip"
>    }
>    ```
>    Sort `top_features` by absolute SHAP value descending. Include all 8 features.
>
> 3. SHAP computation can be slow. Wrap it in a try/except — if it fails for any reason (model structure mismatch, memory, timeout), set `shap_explanation` to `null` and log the error. Never let SHAP computation crash the classification pipeline.
>
> 4. Update `frontend/index.html`'s SOC Analyst tab to render the real SHAP data when available: show a horizontal bar chart (CSS-only, no JS charting library needed — just colored div bars proportional to SHAP values, green for positive, red for negative) with feature names and actual values. Fall back to the existing static image when `shap_explanation` is null.
>
> 5. The `shap` package is already in `requirements.txt` and was used during training (`ml_pipeline/train_model.py` uses `shap.TreeExplainer`). Don't add new dependencies.

---

## Prompt 4: Email Traffic Class — Real Capture Generation

> **Context**: My IPsec testbed (Docker Compose, strongSwan gateways `moon`/`sun`, clients `alice`/`bob`) generates real encrypted traffic captures for ML training. The traffic generation script is `testbed/scripts/generate_traffic.sh`. It currently generates 6 traffic types per variant: icmp, bulk, video, voip, web, email.
>
> **Problem**: The `email` traffic type captures all fell below the 20-packet flow minimum required by `ml_pipeline/feature_extractor.py`, so the trained model (`models/calibrated_rf_model_real.pkl`) has **zero** real email training examples. The email generation in `generate_traffic.sh` likely uses `nc` (netcat) or a minimal SMTP simulation that produces too few packets.
>
> **What I need you to do**:
>
> 1. Read `testbed/scripts/generate_traffic.sh` and find the email traffic generation section. Diagnose why it produces fewer than 20 packets.
>
> 2. Fix it to produce a realistic email-like traffic pattern that will generate ≥20 ESP-encapsulated packets per capture. Options (pick the most realistic one):
>    - Use `swaks` (Swiss Army Knife for SMTP) to send multiple emails with attachments through the tunnel — this produces realistic SMTP dialogue with multiple DATA segments
>    - Use `msmtp` or `curl smtp://` to send several messages in sequence
>    - If no SMTP tool is available in the Alpine container, use `python3 -c` with `smtplib` to script a multi-message SMTP session against a `python3 -m smtpd` receiver on the other side
>    - As a last resort, simulate email-like traffic shape using `iperf3` with email-like parameters (short bursts, asymmetric, ~5-50KB payloads with pauses between them)
>
> 3. The fix must work for both tunnel-mode variants (traffic flows alice→bob through moon/sun) and transport-mode variants (traffic flows directly moon→sun). See how the existing `generate_traffic.sh` handles this split for other traffic types.
>
> 4. After fixing the script, give me the exact commands to:
>    - Regenerate just the email captures for all 8 variants (without redoing icmp/bulk/video/voip/web)
>    - Re-extract features: `python ml_pipeline/feature_extractor.py` (or the batch_process path)
>    - Retrain the model: `python ml_pipeline/train_model.py`
>    - Verify the email class now has real training examples
>
> 5. Also update `data/raw/dataset_manifest.csv` if new rows are needed for the regenerated email captures.
>
> Important constraint: the containers use **Alpine Linux** (musl, not glibc), so not all tools are available. Check what's already installed in the Dockerfile (`testbed/Dockerfile` or `testbed/Dockerfile.gateway` / `testbed/Dockerfile.client`) before assuming a tool exists.

---

## Prompt 5: Dead File Cleanup + Project Hygiene

> **Context**: My project has accumulated dead/deprecated files that are never imported or called by anything but could confuse a judge reviewing the repo. I need a clean sweep.
>
> **Known dead files** (already confirmed dead via grep for imports, but not yet deleted):
> - `testbed/scripts/setup_strongswan.sh` — uses deprecated `ipsec.conf`/`ipsec.secrets` format, never called
> - `ml_pipeline/generate_synthetic_features.py` — generates fake training data, superseded by real captures
> - `ml_pipeline/generate_iscx_features.py` — generates synthetic "ISCXVPN2016" approximation, never validated against real data
> - `backend/sample_data.py` — 5 hardcoded demo datasets from before the pipeline was real, never imported by current `main.py`
> - `backend/analyzer.py` — old hardcoded analyzer, superseded by `parser/ike_parser.py` + `parser/rule_engine.py`
> - `backend/security_engine.py` — old hardcoded scoring engine, superseded by `parser/rule_engine.py`
>
> **What I need you to do**:
>
> 1. For EACH file above: grep the entire repo (all `.py`, `.sh`, `.md`, `.html`, `.jsx`, `.json` files) to confirm it's truly dead (zero code-level imports/calls). If something still references it, tell me instead of deleting.
>
> 2. For confirmed dead files: don't just delete them. Move them to a new `archive/deprecated/` directory with a `README.md` inside explaining what each file was and why it was deprecated. This way a judge who asks "did you write this?" gets a story ("yes, we wrote it initially, then replaced it with real implementations and archived the originals") instead of a suspicious git history gap.
>
> 3. Check for any other dead files I missed — look for `.py` files that are never imported by any other `.py` file and never in any test, and `.sh` scripts that are never called by any other script or referenced in any documentation as "run this".
>
> 4. Clean up `docker-compose.yml` — remove the deprecated `version:` key that generates a warning on every command.
>
> 5. Check `requirements.txt` against actual imports across the entire codebase. Flag any package that's listed but never imported (dead dependency) and any package that's imported but not listed (missing dependency).
>
> 6. If `ipsecguard_readme.md` and `ps160_readme.md` reference any of the dead files in their "Project Structure" trees, update those trees to reflect the actual current structure.
>
> Show me every change as a diff, and the final `archive/deprecated/README.md` content.
