import os
from fpdf import FPDF
from datetime import datetime
from typing import Dict, Any, Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORTS_DIR = os.path.join(BASE_DIR, "docs", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# Severity → (R, G, B) for color-coded rendering
SEVERITY_COLORS = {
    "CRITICAL": (192, 57, 43),    # Red
    "HIGH":     (211, 84, 0),     # Orange
    "MEDIUM":   (243, 156, 18),   # Yellow-amber
    "PASS":     (39, 174, 96),    # Green
    "INFO":     (127, 140, 141),  # Gray
}


def _severity_color(severity: str):
    return SEVERITY_COLORS.get(severity.upper(), (0, 0, 0))


def _risk_label(score: int) -> str:
    if score >= 90:
        return "LOW RISK"
    elif score >= 70:
        return "MODERATE RISK"
    elif score >= 50:
        return "HIGH RISK"
    else:
        return "CRITICAL RISK"


def _risk_color(score: int):
    if score >= 90:
        return SEVERITY_COLORS["PASS"]
    elif score >= 70:
        return SEVERITY_COLORS["MEDIUM"]
    elif score >= 50:
        return SEVERITY_COLORS["HIGH"]
    else:
        return SEVERITY_COLORS["CRITICAL"]


class IPsecReportPDF(FPDF):
    """Professional PDF report renderer for IPsecGuard AI analysis results."""

    def __init__(self, report_title: str, filename: str):
        super().__init__()
        self.report_title = report_title
        self.analyzed_filename = filename
        self.set_auto_page_break(auto=True, margin=20)

    @staticmethod
    def _safe(text: str) -> str:
        """Replace Unicode chars that Helvetica (latin-1) can't encode."""
        return (text
                .replace("\u2014", "--")   # em-dash
                .replace("\u2013", "-")    # en-dash
                .replace("\u2018", "'")    # left single quote
                .replace("\u2019", "'")    # right single quote
                .replace("\u201c", '"')    # left double quote
                .replace("\u201d", '"')    # right double quote
                .replace("\u2026", "...")  # ellipsis
                .replace("\u00a7", "S.")   # section sign
                .replace("\u2264", "<=")   # less-than-or-equal
                .replace("\u2265", ">=")   # greater-than-or-equal
                )

    def header(self):
        self.set_font("helvetica", "B", 13)
        self.set_text_color(41, 128, 185)
        self.cell(0, 8, "IPsecGuard AI", border=False, new_x="RIGHT", new_y="TOP", align="L")
        self.set_font("helvetica", "", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", align="R", new_x="LMARGIN", new_y="NEXT")

        self.set_font("helvetica", "B", 10)
        self.set_text_color(80, 80, 80)
        self.cell(0, 6, self.report_title, new_x="LMARGIN", new_y="NEXT", align="L")

        self.set_draw_color(41, 128, 185)
        self.set_line_width(0.6)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 7)
        self.set_text_color(160, 160, 160)
        self.cell(0, 10, f"IPsecGuard AI  |  {self.analyzed_filename}  |  Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title: str):
        self.set_font("helvetica", "B", 11)
        self.set_text_color(44, 62, 80)
        self.set_fill_color(234, 237, 240)
        self.cell(0, 8, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        self.ln(3)

    def subsection_title(self, title: str):
        self.set_font("helvetica", "B", 10)
        self.set_text_color(52, 73, 94)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def metric(self, label: str, value: str, color: tuple = (0, 0, 0)):
        self.set_font("helvetica", "B", 9)
        self.set_text_color(60, 60, 60)
        self.cell(65, 6, f"{label}:", border=False)
        self.set_font("helvetica", "B", 9)
        self.set_text_color(*color)
        self.cell(0, 6, self._safe(str(value)), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def body_text(self, text: str):
        self.set_font("helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5, self._safe(text))
        self.ln(2)

    def italic_text(self, text: str):
        self.set_font("helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.multi_cell(0, 4.5, self._safe(text))
        self.ln(2)

    def colored_badge(self, text: str, color: tuple):
        self.set_font("helvetica", "B", 9)
        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)

        self.cell(self.get_string_width(text) + 8, 7, text, fill=True, ln=False)
        self.set_text_color(0, 0, 0)
        self.set_fill_color(255, 255, 255)

    def risk_score_block(self, score: int):
        """Renders a prominent risk score display."""
        label = _risk_label(score)
        color = _risk_color(score)

        self.ln(2)
        # Score box
        self.set_font("helvetica", "B", 28)
        self.set_text_color(*color)
        self.cell(40, 18, f"{score}", align="C", ln=False)
        self.set_font("helvetica", "", 14)
        self.set_text_color(120, 120, 120)
        self.cell(10, 18, "/ 100", align="L", ln=False)

        self.set_font("helvetica", "B", 12)
        self.set_text_color(*color)
        self.cell(0, 18, label, align="L", ln=True)
        self.set_text_color(0, 0, 0)

        # Score bar
        bar_width = 130
        self.set_fill_color(220, 220, 220)
        bar_y = self.get_y()
        self.rect(10, bar_y, bar_width, 4, style="F")
        self.set_fill_color(*color)
        self.rect(10, bar_y, bar_width * (score / 100), 4, style="F")
        self.ln(8)

    def findings_table(self, findings: list):
        """Renders a severity-coded findings list."""
        for f in findings:
            sev = f.get("severity", "INFO")
            cap = f.get("cap_applied", "?")
            msg = f.get("message", "")
            color = _severity_color(sev)

            # Severity badge + cap on one line
            self.set_font("helvetica", "B", 8)
            self.set_fill_color(*color)
            self.set_text_color(255, 255, 255)
            badge = f" {sev} "
            self.cell(self.get_string_width(badge) + 4, 5.5, badge, fill=True, new_x="RIGHT", new_y="TOP")

            self.set_text_color(100, 100, 100)
            self.set_fill_color(255, 255, 255)
            self.set_font("helvetica", "", 8)
            self.cell(20, 5.5, f"  Cap: {cap}", new_x="RIGHT", new_y="TOP")

            # Message wraps below
            self.set_text_color(40, 40, 40)
            self.set_font("helvetica", "", 8)
            remaining_w = self.w - self.r_margin - self.get_x()
            if remaining_w < 30:
                # Not enough room on this line, wrap to next
                self.ln(5.5)
                self.multi_cell(0, 5, f"  {msg}")
            else:
                self.multi_cell(remaining_w, 5.5, msg)

            self.ln(1.5)

        self.ln(2)


def _render_compliance_section(pdf: IPsecReportPDF, data: Dict[str, Any], detailed: bool = False):
    """Renders compliance section. Works for both executive and technical."""
    compliance = data.get("compliance", {})
    status = compliance.get("status", "indeterminate")

    if status == "indeterminate":
        pdf.section_title("Compliance Assessment")
        reason = compliance.get("reason", "Compliance could not be assessed.")
        pdf.body_text(f"Status: INDETERMINATE — {reason}")

        # Even when IKE compliance is indeterminate, replay/metadata may have data
        _render_replay_readiness(pdf, compliance, detailed)
        _render_metadata_exposure(pdf, compliance, detailed)
        _render_key_lifetime(pdf, compliance)
        return

    score = compliance.get("score", 0)
    findings = compliance.get("findings", [])
    threat_matrix = compliance.get("threat_matrix", [])
    raw = compliance.get("raw_parameters", {})
    caveats = compliance.get("caveats", [])

    # --- Score ---
    pdf.section_title("Compliance Score")
    pdf.risk_score_block(score)

    # --- Executive summary of what's wrong ---
    critical_count = sum(1 for f in findings if f.get("severity") == "CRITICAL")
    high_count = sum(1 for f in findings if f.get("severity") == "HIGH")
    medium_count = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    pass_count = sum(1 for f in findings if f.get("severity") == "PASS")

    summary_parts = []
    if critical_count:
        summary_parts.append(f"{critical_count} CRITICAL")
    if high_count:
        summary_parts.append(f"{high_count} HIGH")
    if medium_count:
        summary_parts.append(f"{medium_count} MEDIUM")
    if pass_count:
        summary_parts.append(f"{pass_count} PASS")

    if summary_parts:
        pdf.body_text(f"Findings breakdown: {', '.join(summary_parts)}.")

    if threat_matrix:
        pdf.body_text(f"Active threats: {'; '.join(threat_matrix[:3])}{'...' if len(threat_matrix) > 3 else ''}")

    # --- SA Parameters (technical only) ---
    if detailed and raw:
        pdf.section_title("Security Association Parameters")
        pdf.body_text("Parsed from cleartext IKE_SA_INIT exchange (RFC 7296 binary decoding):")
        pdf.metric("IKE Version", raw.get("ike_version", "UNKNOWN"))
        enc = raw.get("encryption_algorithm", [])
        pdf.metric("Encryption", ", ".join(enc) if enc else "Not observed")
        integ = raw.get("integrity_algorithm", [])
        pdf.metric("Integrity", ", ".join(integ) if integ else "N/A (AEAD cipher provides built-in integrity)")
        prf = raw.get("prf_algorithm", [])
        pdf.metric("PRF", ", ".join(prf) if prf else "Not observed")
        dh = raw.get("dh_group", [])
        pdf.metric("DH Group", ", ".join(dh) if dh else "Not observed")
        pdf.ln(2)

    # --- Findings table (technical), summary (executive) ---
    if detailed and findings:
        pdf.section_title("Detailed Findings")
        pdf.findings_table(findings)
    elif findings:
        pdf.section_title("Key Findings")
        for f in findings:
            if f.get("severity") in ("CRITICAL", "HIGH"):
                color = _severity_color(f["severity"])
                pdf.set_font("helvetica", "B", 9)
                pdf.set_text_color(*color)
                sev_text = f"[{f['severity']}] "
                pdf.cell(pdf.get_string_width(sev_text) + 2, 5, sev_text, ln=False)
                pdf.set_font("helvetica", "", 9)
                pdf.set_text_color(40, 40, 40)
                pdf.multi_cell(0, 5, f["message"])
                pdf.ln(1)

    # --- Replay, Metadata, Key Lifetime ---
    _render_replay_readiness(pdf, compliance, detailed)
    _render_metadata_exposure(pdf, compliance, detailed)
    _render_key_lifetime(pdf, compliance)

    # --- Caveats ---
    if caveats:
        pdf.section_title("Caveats & Limitations")
        for c in caveats:
            pdf.italic_text(f"* {c}")


def _render_replay_readiness(pdf: IPsecReportPDF, compliance: Dict, detailed: bool):
    replay = compliance.get("replay_readiness", {})
    if not replay:
        return

    status = replay.get("status", "indeterminate")
    if status == "indeterminate":
        if detailed:
            pdf.subsection_title("Replay Protection Readiness")
            pdf.body_text(f"Indeterminate: {replay.get('reason', 'No ESP data available.')}")
        return

    result = replay.get("result", "UNKNOWN")
    severity = replay.get("severity", "INFO")
    message = replay.get("message", "")
    caveat = replay.get("caveat", "")
    color = _severity_color(severity)

    pdf.subsection_title("Replay Protection Readiness")
    pdf.metric("ESP Sequence Number Check", result, color)
    pdf.body_text(message)
    if caveat and detailed:
        pdf.italic_text(caveat)


def _render_metadata_exposure(pdf: IPsecReportPDF, compliance: Dict, detailed: bool):
    meta = compliance.get("metadata_exposure", {})
    if not meta:
        return

    status = meta.get("status", "indeterminate")
    if status == "indeterminate":
        if detailed:
            pdf.subsection_title("Metadata Exposure Assessment")
            pdf.body_text(f"Indeterminate: {meta.get('reason', 'Classifier data unavailable.')}")
        return

    severity = meta.get("severity", "INFO")
    confidence = meta.get("classifier_confidence", 0)
    message = meta.get("message", "")
    color = _severity_color(severity)

    pdf.subsection_title("Traffic Analysis Resistance")
    pdf.metric("Metadata Exposure", f"{severity} ({confidence:.1f}% classifier confidence)", color)
    pdf.body_text(message)


def _render_key_lifetime(pdf: IPsecReportPDF, compliance: Dict):
    kl = compliance.get("key_lifetime_status", {})
    if not kl:
        return
    if kl.get("status") == "not_assessable":
        pdf.subsection_title("Key Lifetime")
        pdf.italic_text(f"Not assessable: {kl.get('reason', 'SA lifetimes are local policy, not observable on the wire.')}")


def _render_classification_section(pdf: IPsecReportPDF, data: Dict[str, Any], detailed: bool = False):
    classification = data.get("classification", {})
    status = classification.get("status", "indeterminate")

    pdf.section_title("Traffic Classification (ML)")

    if status == "indeterminate":
        pdf.body_text(f"Indeterminate: {classification.get('reason', 'Classification could not be performed.')}")
        return

    if status == "unavailable":
        pdf.body_text(f"Unavailable: {classification.get('reason', 'No trained model found.')}")
        return

    # Classified
    predicted = classification.get("predicted_class", "unknown")
    confidence = classification.get("confidence", 0)
    flow_stats = classification.get("flow_stats", {})
    cm = classification.get("countermeasures", {})

    conf_color = _severity_color("HIGH") if confidence > 90 else _severity_color("MEDIUM") if confidence > 70 else _severity_color("PASS")

    pdf.metric("Predicted Traffic Type", predicted.upper(), conf_color)
    pdf.metric("Classification Confidence", f"{confidence:.1f}%", conf_color)

    if confidence > 90:
        pdf.body_text(
            f"A passive adversary can classify this tunnel's encrypted traffic as "
            f"'{predicted}' with {confidence:.1f}% confidence using flow-level "
            f"metadata alone. This represents significant metadata leakage."
        )
    elif confidence > 70:
        pdf.body_text(
            f"The tunnel shows moderate metadata leakage — traffic classified as "
            f"'{predicted}' with {confidence:.1f}% confidence."
        )
    else:
        pdf.body_text(
            f"Classifier confidence is {confidence:.1f}% ('{predicted}'), suggesting "
            f"reasonable traffic analysis resistance at this confidence level."
        )

    # Flow stats (technical)
    if detailed and flow_stats:
        pdf.subsection_title("Flow Statistics")
        pdf.metric("Packet Count", str(flow_stats.get("pkt_count", "?")))
        pdf.metric("Mean Packet Length", f"{flow_stats.get('mean_len', 0):.1f} bytes")
        pdf.metric("Mean Inter-Arrival Time", f"{flow_stats.get('mean_iat', 0):.4f} s")
        pdf.metric("Direction Ratio", f"{flow_stats.get('direction_ratio', 0):.2f}")
        pdf.ln(2)

    # Countermeasures
    if cm:
        pdf.subsection_title("Countermeasure Simulation")
        pdf.body_text("Simulated Traffic Flow Confidentiality (TFC) padding countermeasures:")

        mtu_oh = cm.get("mtu_overhead_pct", 0)
        mtu_conf = cm.get("mtu_confidence", 0)
        adapt_oh = cm.get("adaptive_overhead_pct", 0)
        adapt_conf = cm.get("adaptive_confidence", 0)

        pdf.metric("MTU Padding", f"{confidence:.1f}% -> {mtu_conf:.1f}% confidence  |  {mtu_oh:.1f}% bandwidth overhead")
        pdf.metric("Adaptive Padding", f"{confidence:.1f}% -> {adapt_conf:.1f}% confidence  |  {adapt_oh:.1f}% bandwidth overhead")

        if detailed:
            # Recommend the better countermeasure
            mtu_drop = confidence - mtu_conf
            adapt_drop = confidence - adapt_conf
            if mtu_drop > adapt_drop and mtu_oh <= adapt_oh * 1.2:
                pdf.body_text(
                    f"Recommendation: MTU padding provides better confidence reduction "
                    f"({mtu_drop:.1f}pp) at lower bandwidth cost ({mtu_oh:.1f}%)."
                )
            elif adapt_drop > 0:
                pdf.body_text(
                    f"Recommendation: Adaptive padding provides {adapt_drop:.1f}pp "
                    f"confidence reduction at {adapt_oh:.1f}% bandwidth cost."
                )
        pdf.ln(2)


def _render_mode_inference_section(pdf: IPsecReportPDF, data: Dict[str, Any]):
    mode = data.get("mode_inference", {})
    status = mode.get("status", "indeterminate")

    pdf.subsection_title("Tunnel/Transport Mode Inference")

    if status == "indeterminate":
        pdf.body_text(f"Indeterminate: {mode.get('reason', 'Mode inference unavailable.')}")
        return

    if status == "unavailable":
        pdf.body_text(f"Unavailable: {mode.get('reason', 'No mode classifier found.')}")
        return

    predicted_mode = mode.get("predicted_mode", "unknown")
    reliability = mode.get("reliability", "UNKNOWN")
    accuracy = mode.get("validated_balanced_accuracy", 0)

    pdf.metric("Inferred Mode", predicted_mode.title(), _severity_color("MEDIUM"))
    pdf.metric("Reliability", reliability, _severity_color("HIGH") if reliability == "LOW" else (0, 0, 0))
    pdf.metric("Validated Balanced Accuracy", f"{accuracy:.2f}")
    pdf.italic_text(
        "Note: Mode is never visible in cleartext IKE fields (it is negotiated inside the "
        "encrypted IKE_AUTH exchange). This is a statistical inference from ESP ciphertext "
        "payload length, NOT a protocol extraction. The validated accuracy is close to chance "
        "level (0.50) — treat this prediction as indicative, not confirmed."
    )


def _render_recommended_actions(pdf: IPsecReportPDF, data: Dict[str, Any]):
    """Generates actionable recommendations from actual findings — never hardcoded."""
    compliance = data.get("compliance", {})
    classification = data.get("classification", {})
    findings = compliance.get("findings", [])

    actions = []

    for f in findings:
        sev = f.get("severity", "")
        msg = f.get("message", "")

        if "IKEv1" in msg:
            actions.append(("CRITICAL", "Migrate all IKE endpoints from IKEv1 to IKEv2 immediately. IKEv1 is deprecated per RFC 8247 and exposes the deployment to offline dictionary attacks."))
        elif "DES" in msg and "3DES" not in msg:
            actions.append(("CRITICAL", "Replace DES encryption with AES-GCM-256 or CHACHA20-POLY1305. DES provides zero effective confidentiality against modern compute."))
        elif "3DES" in msg or "SWEET32" in msg:
            actions.append(("HIGH", "Replace 3DES with AES-GCM-256. 3DES is vulnerable to SWEET32 birthday attacks (CVE-2016-2183) after ~32GB of traffic."))
        elif "MD5" in msg:
            actions.append(("CRITICAL", "Replace MD5 integrity with SHA-256 or SHA-384. MD5 is cryptographically broken with practical collision attacks."))
        elif "SHA1" in msg and sev in ("MEDIUM", "HIGH"):
            actions.append(("MEDIUM", "Transition SHA-1 integrity to SHA-256. SHA-1 has known theoretical collision weaknesses and is deprecated for new deployments."))
        elif "Group 1" in msg or "Group 2" in msg or "1024" in msg or "768" in msg:
            actions.append(("HIGH", "Upgrade DH group to Group 19 (ECP-256) or Group 20 (ECP-384). Groups 1/2 provide less than 112 bits of security and are vulnerable to the Logjam attack."))
        elif "Group 5" in msg or "1536" in msg:
            actions.append(("HIGH", "Upgrade DH group from Group 5 (1536-bit) to Group 19 (ECP-256) or higher. Group 5 provides marginal security."))
        elif "Forward Secrecy" in msg or "PFS" in msg:
            actions.append(("HIGH", "Enable Perfect Forward Secrecy (PFS) on all Child SAs. Without PFS, compromise of the IKE SA key exposes all past and future ESP traffic."))
        elif "AES-CBC" in msg:
            actions.append(("MEDIUM", "Transition from AES-CBC to AES-GCM (AEAD). AES-CBC is being phased out and requires careful MAC-then-encrypt ordering to avoid padding oracle attacks."))

    # Metadata exposure recommendation
    meta = compliance.get("metadata_exposure", {})
    if meta.get("severity") in ("HIGH", "MEDIUM"):
        conf = meta.get("classifier_confidence", 0)
        actions.append(("MEDIUM", f"Deploy traffic padding countermeasures (RFC 4303 TFC padding, MTU padding, or adaptive padding) to reduce metadata leakage. Current classifier confidence: {conf:.1f}%."))

    if not actions:
        return

    pdf.section_title("Recommended Actions")
    seen = set()
    for priority, action in actions:
        if action in seen:
            continue
        seen.add(action)
        color = _severity_color(priority)
        pdf.set_font("helvetica", "B", 8)
        pdf.set_text_color(*color)
        badge = f"[{priority}] "
        pdf.cell(pdf.get_string_width(badge) + 1, 5, badge, ln=False)
        pdf.set_font("helvetica", "", 8)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 5, action)
        pdf.ln(1)


def _render_capture_summary(pdf: IPsecReportPDF, data: Dict[str, Any]):
    capture = data.get("capture_summary", {})
    if not capture:
        return

    pdf.section_title("Capture Summary")
    pdf.metric("Filename", data.get("filename", "unknown"))
    pdf.metric("Total Packets", str(capture.get("total_packets", 0)))
    pdf.metric("IKE Packets", str(capture.get("ike_packets", 0)))
    pdf.metric("ESP Packets", str(capture.get("esp_packets", 0)))
    pdf.ln(2)


# =====================================================================
# Public API — called by main.py's /export endpoint
# =====================================================================

def generate_executive_report(data: Dict[str, Any]) -> str:
    """
    Generates a 1-2 page executive PDF for a CISO from real analysis data.

    Returns the absolute path to the generated PDF file.
    """
    filename = data.get("filename", "unknown.pcap")
    pdf = IPsecReportPDF("Executive Security Assessment", filename)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Handle error status
    if data.get("status") == "error":
        pdf.section_title("Analysis Error")
        pdf.body_text(f"Analysis of '{filename}' failed: {data.get('error', 'Unknown error')}")
        out_path = os.path.join(REPORTS_DIR, "Executive_Report.pdf")
        pdf.output(out_path)
        return out_path

    # Title
    pdf.set_font("helvetica", "B", 15)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 12, "Executive Summary", ln=True)
    pdf.ln(2)

    # Compliance
    _render_compliance_section(pdf, data, detailed=False)

    # Classification summary
    _render_classification_section(pdf, data, detailed=False)

    # Recommended actions
    _render_recommended_actions(pdf, data)

    out_path = os.path.join(REPORTS_DIR, "Executive_Report.pdf")
    pdf.output(out_path)
    return out_path


def generate_technical_report(data: Dict[str, Any]) -> str:
    """
    Generates a 3-5 page technical PDF for a security engineer from real
    analysis data.

    Returns the absolute path to the generated PDF file.
    """
    filename = data.get("filename", "unknown.pcap")
    pdf = IPsecReportPDF("Technical Security Assessment", filename)
    pdf.alias_nb_pages()
    pdf.add_page()

    # Handle error status
    if data.get("status") == "error":
        pdf.section_title("Analysis Error")
        pdf.body_text(f"Analysis of '{filename}' failed: {data.get('error', 'Unknown error')}")
        out_path = os.path.join(REPORTS_DIR, "Technical_Report.pdf")
        pdf.output(out_path)
        return out_path

    # Title
    pdf.set_font("helvetica", "B", 15)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 12, "Technical Assessment Report", ln=True)
    pdf.ln(2)

    # Capture summary
    _render_capture_summary(pdf, data)

    # Compliance (detailed)
    _render_compliance_section(pdf, data, detailed=True)

    # Classification (detailed)
    pdf.add_page()
    _render_classification_section(pdf, data, detailed=True)

    # Mode inference
    _render_mode_inference_section(pdf, data)

    # Recommended actions
    _render_recommended_actions(pdf, data)

    # Scope & limitations
    pdf.section_title("Scope & Threat Model Limitations")
    pdf.body_text(
        "1. Adversary Model: Results model a closed-world, strong passive adversary with "
        "access to the encrypted traffic only. Active attacks (MITM, delay injection) are "
        "explicitly out of scope — IPsec's ICV and anti-replay mechanisms address those."
    )
    pdf.body_text(
        "2. Micro-flow Exclusion: A strict 20-packet minimum was enforced during SPLT feature "
        "extraction. Flows below this threshold are reported as indeterminate, not classified."
    )
    pdf.body_text(
        "3. Passive Capture Limits: SA lifetimes, anti-replay window size, and receiver-side "
        "enforcement are local policy, never visible on the wire. These are documented as "
        "'not assessable' rather than assumed."
    )

    out_path = os.path.join(REPORTS_DIR, "Technical_Report.pdf")
    pdf.output(out_path)
    return out_path


if __name__ == "__main__":
    # Demo with minimal data to verify rendering
    demo_data = {
        "status": "completed",
        "filename": "demo_capture.pcap",
        "capture_summary": {"total_packets": 150, "ike_packets": 4, "esp_packets": 146},
        "compliance": {
            "status": "assessed",
            "score": 59,
            "risk_score": 41,
            "findings": [
                {"severity": "PASS", "message": "IKEv2 compliant.", "cap_applied": 100},
                {"severity": "PASS", "message": "Modern AEAD encryption (RFC 8221).", "cap_applied": 100},
                {"severity": "HIGH", "message": "Group 2 (1024-bit) provides <112 bits of security (Logjam).", "cap_applied": 59},
            ],
            "threat_matrix": ["Group 2 (1024-bit) provides <112 bits of security (Logjam)."],
            "raw_parameters": {
                "ike_version": "IKEv2",
                "encryption_algorithm": ["AES-GCM-256"],
                "integrity_algorithm": [],
                "prf_algorithm": ["SHA256"],
                "dh_group": ["MODP_1024"],
            },
            "key_lifetime_status": {"status": "not_assessable", "reason": "SA lifetimes are local policy per RFC 7296 section 2.8."},
            "replay_readiness": {"status": "assessed", "result": "MONOTONIC", "severity": "PASS", "message": "ESP sequence numbers are monotonically incrementing.", "caveat": "Sender-side compliance only."},
            "metadata_exposure": {"status": "assessed", "severity": "HIGH", "classifier_confidence": 92.5, "message": "Tunnel is highly transparent to traffic analysis."},
            "caveats": ["PFS status could not be determined: no CREATE_CHILD_SA rekey observed."],
        },
        "classification": {
            "status": "classified",
            "predicted_class": "voip",
            "confidence": 92.5,
            "flow_stats": {"pkt_count": 200, "mean_len": 148.5, "mean_iat": 0.021, "direction_ratio": 0.52},
            "countermeasures": {"mtu_overhead_pct": 14.2, "mtu_confidence": 77.0, "adaptive_overhead_pct": 17.0, "adaptive_confidence": 87.3},
        },
        "mode_inference": {
            "status": "inferred",
            "predicted_mode": "tunnel",
            "reliability": "LOW",
            "validated_balanced_accuracy": 0.55,
        },
    }

    print("Generating Executive Report...")
    generate_executive_report(demo_data)
    print("Generating Technical Report...")
    generate_technical_report(demo_data)
    print(f"Reports generated in {REPORTS_DIR}/")
