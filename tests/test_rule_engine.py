import pytest
import os
import sys

# Add parent directory to path to import parser modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from parser.rule_engine import SecurityRuleEngine
from parser.ike_parser import IKEParser

# =======================================================
# 1. Tests for the Severity-Cap Rule Engine
# =======================================================

def test_engine_known_good_strong_aead():
    """Test 1: Known Good - Strong AEAD (AES-GCM-256) with ECP256 and PFS."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "integrity_algorithm": [], # GCM doesn't need separate integrity
        "dh_group": ["ECP_256"],
        "pfs": True,
        "mode": "Tunnel"
    }
    engine = SecurityRuleEngine(data, rules_file="nist_rules.json")
    result = engine.evaluate()
    assert result["security_score"] == 100
    assert result["risk_score"] == 0
    assert len(result["threat_matrix"]) == 0

def test_engine_known_good_modern_ecc():
    """Test 2: Known Good - Modern ECC (Curve25519) + AES-GCM-128."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-128"],
        "dh_group": ["Curve25519"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 100

def test_engine_known_good_baseline_cbc():
    """Test 3: Known Good - Baseline CBC (AES-CBC-256) with SHA256. (Passes with Medium cap 79)"""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-CBC-256"],
        "integrity_algorithm": ["SHA256"],
        "dh_group": ["MODP_2048"], # Group 14 (Cap 90)
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    # CBC-256 caps at 79. Group 14 caps at 90. Final score should be min(100, 79, 90) = 79.
    assert result["security_score"] == 79
    assert result["risk_score"] == 21

def test_engine_known_good_transport_mode():
    """Test 4: Known Good - Transport mode strong config."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["CHACHA20-POLY1305"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "mode": "Transport"
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 100

def test_engine_known_good_group14_baseline():
    """Test 5: Known Good - Acceptable minimum (Group 14)."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["MODP_2048"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 90 # Group 14 caps at 90

def test_engine_known_bad_ikev1():
    """Test 6: Known Bad - IKEv1 caps score to 25."""
    data = {
        "ike_version": "IKEv1",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 25
    assert "IKEv1" in result["threat_matrix"][0]

def test_engine_known_bad_3des():
    """Test 7: Known Bad - 3DES legacy cipher (SWEET32). Caps at 59."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["3DES"],
        "integrity_algorithm": ["SHA1"],
        "dh_group": ["MODP_2048"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 59
    assert any("3DES" in t for t in result["threat_matrix"])

def test_engine_known_bad_group2_logjam():
    """Test 8: Known Bad - DH Group 2 (1024-bit). Caps at 59."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["MODP_1024"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 59
    assert any("Group 2" in t or "1024" in t for t in result["threat_matrix"])

def test_engine_known_bad_no_pfs():
    """Test 9: Known Bad - Perfect Forward Secrecy disabled."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": False
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] <= 59 # Rule engine caps no-PFS at 59
    assert any("Perfect Forward Secrecy" in t for t in result["threat_matrix"])

def test_engine_known_bad_md5():
    """Test 10: Known Bad - MD5 integrity (broken). Caps at 25."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-CBC-256"],
        "integrity_algorithm": ["MD5"],
        "dh_group": ["MODP_2048"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["security_score"] == 25

# =======================================================
# 1b. Tests for Key Lifetime Status (Structural Limitation)
# =======================================================

def test_engine_key_lifetime_not_assessable():
    """Test 11: Key lifetime is always reported as not assessable —
    SA lifetimes are local policy per RFC 7296 §2.8, never on the wire."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True
    }
    result = SecurityRuleEngine(data).evaluate()
    assert "key_lifetime_status" in result
    assert result["key_lifetime_status"]["status"] == "not_assessable"
    assert "RFC 7296" in result["key_lifetime_status"]["reason"]
    # Must NOT affect the security score — this is a documentation field,
    # not a scored finding.
    assert result["security_score"] == 100

# =======================================================
# 1c. Tests for Replay Readiness (ESP Sequence Numbers)
# =======================================================

def test_engine_replay_readiness_monotonic():
    """Test 12: Monotonically incrementing ESP sequence numbers → PASS.
    Verifies sender compliance with RFC 4303 §3.3.3."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "esp_seq_by_spi": {
            "0x0000abcd": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "0x0000ef01": [1, 2, 3, 4, 5],
        }
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["replay_readiness"]["status"] == "assessed"
    assert result["replay_readiness"]["result"] == "MONOTONIC"
    assert result["replay_readiness"]["severity"] == "PASS"
    # PASS finding should NOT cap the score
    assert result["security_score"] == 100

def test_engine_replay_readiness_duplicate_seq():
    """Test 13: Duplicate ESP sequence numbers → HIGH severity.
    Sender is violating RFC 4303 §3.3.3 (MUST NOT duplicate)."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "esp_seq_by_spi": {
            "0x0000abcd": [1, 2, 3, 3, 4, 5],  # duplicate seq 3
        }
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["replay_readiness"]["status"] == "assessed"
    assert result["replay_readiness"]["result"] == "DUPLICATE_SEQ"
    assert result["replay_readiness"]["severity"] == "HIGH"
    # HIGH finding caps score to 59
    assert result["security_score"] <= 59
    assert any("Duplicate ESP sequence" in t for t in result["threat_matrix"])

def test_engine_replay_readiness_non_monotonic():
    """Test 14: Non-monotonic (out-of-order) ESP sequence numbers → MEDIUM."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "esp_seq_by_spi": {
            "0x0000abcd": [1, 2, 5, 4, 6, 7],  # 4 comes after 5
        }
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["replay_readiness"]["status"] == "assessed"
    assert result["replay_readiness"]["result"] == "NON_MONOTONIC"
    assert result["replay_readiness"]["severity"] == "MEDIUM"
    assert result["security_score"] <= 79

def test_engine_replay_readiness_no_esp():
    """Test 15: No ESP data → indeterminate (not a finding)."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        # No esp_seq_by_spi key at all
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["replay_readiness"]["status"] == "indeterminate"
    # Must NOT affect the security score
    assert result["security_score"] == 100

def test_engine_replay_readiness_empty_esp():
    """Test 16: Empty ESP data dict → indeterminate."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "esp_seq_by_spi": {}
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["replay_readiness"]["status"] == "indeterminate"
    assert result["security_score"] == 100

# =======================================================
# 1d. Tests for Metadata Exposure (Classifier Confidence)
# =======================================================

def test_engine_metadata_exposure_high():
    """Test 17: High classifier confidence (>90%) → HIGH metadata exposure.
    Tunnel is highly transparent to traffic analysis."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "classifier_confidence": 95.0
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["metadata_exposure"]["status"] == "assessed"
    assert result["metadata_exposure"]["severity"] == "HIGH"
    assert result["metadata_exposure"]["classifier_confidence"] == 95.0
    # HIGH finding caps score to 59
    assert result["security_score"] <= 59
    assert any("metadata exposure" in t.lower() for t in result["threat_matrix"])

def test_engine_metadata_exposure_medium():
    """Test 18: Medium classifier confidence (70-90%) → MEDIUM."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "classifier_confidence": 80.0
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["metadata_exposure"]["status"] == "assessed"
    assert result["metadata_exposure"]["severity"] == "MEDIUM"
    assert result["security_score"] <= 79

def test_engine_metadata_exposure_low():
    """Test 19: Low classifier confidence (<70%) → PASS."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        "classifier_confidence": 55.0
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["metadata_exposure"]["status"] == "assessed"
    assert result["metadata_exposure"]["severity"] == "PASS"
    # PASS — no cap applied
    assert result["security_score"] == 100

def test_engine_metadata_exposure_no_classifier():
    """Test 20: No classifier data → indeterminate (not a finding)."""
    data = {
        "ike_version": "IKEv2",
        "encryption_algorithm": ["AES-GCM-256"],
        "dh_group": ["ECP_256"],
        "pfs": True,
        # No classifier_confidence key
    }
    result = SecurityRuleEngine(data).evaluate()
    assert result["metadata_exposure"]["status"] == "indeterminate"
    assert result["security_score"] == 100


# =======================================================
# 2. Tests for the IKE Parser (Scapy Extraction)
# =======================================================
try:
    from scapy.all import ISAKMP
    SCAPY_INSTALLED = True
except ImportError:
    SCAPY_INSTALLED = False

import os

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
REAL_IKE_PCAP = os.path.join(FIXTURE_DIR, "real_ike_sa_init_aes256gcm_ecp256.pcap")


@pytest.mark.skipif(not SCAPY_INSTALLED, reason="Scapy is not installed in this environment")
def test_parser_extraction_real_pcap():
    """
    Tests IKEParser against a REAL captured IKE_SA_INIT exchange (strongSwan,
    tunnel-aes256gcm-ecp256-pfs variant, testbed session 2026-09-22), not a
    hand-written mock.

    This replaces a previous mock-based test that only ever validated the
    parser's OLD implementation, which searched Scapy's `pkt.show(dump=True)`
    text output for literal substrings like "AES_GCM_16_256" and "Group 19".
    That never worked against real traffic: Scapy's ISAKMP dissector doesn't
    render SA/Proposal/Transform payloads as readable text at all, it only
    exposes them as raw undissected bytes. The mock "passed" only because it
    fed the parser a string containing exactly the substrings it searched
    for - a real capture proved this out directly (see ike_parser.py's
    docstring and the byte-level RFC 7296 parsing it now does instead).

    Expected values below were independently verified two ways for this
    exact capture: (1) hand-decoding the raw SA payload bytes per RFC 7296
    Section 3.3, and (2) the live `swanctl --list-sas` output at capture time
    reporting the negotiated proposal as "AES_GCM_16-256/PRF_HMAC_SHA2_256/ECP_256".
    """
    assert os.path.exists(REAL_IKE_PCAP), f"Missing test fixture: {REAL_IKE_PCAP}"

    res = IKEParser(REAL_IKE_PCAP).parse()

    assert res["ike_version"] == "IKEv2"
    assert "AES-GCM-256" in res["encryption_algorithm"]
    assert "SHA256" in res["prf_algorithm"]
    assert "ECP_256" in res["dh_group"]
    # AES-GCM is AEAD - the proposal has no separate integrity transform at
    # all (verified: the raw SA payload has only 3 transforms: ENCR/PRF/DH).
    # See test_parser_extraction_real_pcap_cbc_hmac below for the contrasting
    # CBC+HMAC case, which DOES have a 4th, separate integrity transform.
    assert res["integrity_algorithm"] == []

    # mode/pfs are NOT extractable from a passive IKE_SA_INIT-only capture -
    # both are negotiated inside the encrypted IKE_AUTH/CREATE_CHILD_SA
    # exchange. Asserting the honest "unknown" defaults here, not a guess.
    assert res["mode"] == "UNKNOWN"
    assert res["pfs"] is False


CBC_HMAC_IKE_PCAP = os.path.join(FIXTURE_DIR, "real_ike_sa_init_aes256cbc_sha1_modp2048.pcap")
WEAK_LEGACY_IKE_PCAP = os.path.join(FIXTURE_DIR, "real_ike_sa_init_3des_sha1_modp1024.pcap")


@pytest.mark.skipif(not SCAPY_INSTALLED, reason="Scapy is not installed in this environment")
def test_parser_extraction_real_pcap_cbc_hmac():
    """
    Tests IKEParser against a REAL captured IKE_SA_INIT exchange using a
    CBC+HMAC proposal (strongSwan, tunnel-aes256cbc-sha1-modp2048-nopfs
    variant, testbed session 2026-09-22) - a code path the AES-GCM fixture
    above never exercises, since AEAD ciphers have no separate integrity
    transform. This is the main thing that test couldn't verify:
    `integrity_algorithm` should come back POPULATED here, not empty.

    Expected values verified two ways for this exact capture: (1) hand-decoding
    the raw SA payload bytes per RFC 7296 Section 3.3 - 4 transforms present
    (Encryption id=12/ENCR_AES_CBC + Key Length attr=256, Integrity id=2/
    AUTH_HMAC_SHA1_96, PRF id=2/PRF_HMAC_SHA1, DH id=14/MODP_2048) - and (2)
    the live `swanctl --list-sas` output at capture time reporting the
    negotiated proposal as "AES_CBC-256/HMAC_SHA1_96/PRF_HMAC_SHA1/MODP_2048".
    Both agree exactly; the parser needed no fixes for this proposal shape.
    """
    assert os.path.exists(CBC_HMAC_IKE_PCAP), f"Missing test fixture: {CBC_HMAC_IKE_PCAP}"

    res = IKEParser(CBC_HMAC_IKE_PCAP).parse()

    assert res["ike_version"] == "IKEv2"
    assert "AES-CBC-256" in res["encryption_algorithm"]
    assert "SHA1" in res["integrity_algorithm"]
    assert "SHA1" in res["prf_algorithm"]
    assert "MODP_2048" in res["dh_group"]
    assert res["mode"] == "UNKNOWN"
    assert res["pfs"] is False


@pytest.mark.skipif(not SCAPY_INSTALLED, reason="Scapy is not installed in this environment")
def test_parser_extraction_real_pcap_weak_legacy():
    """
    Tests IKEParser against a REAL captured IKE_SA_INIT exchange using a
    weak/legacy proposal (strongSwan, tunnel-weak-3des-sha1-modp1024 variant,
    testbed session 2026-09-22) - different Transform ID values entirely from
    both fixtures above (ENCR_3DES=3, not ENCR_AES_CBC=12 or ENCR_AES_GCM_16=20;
    MODP_1024/Group 2=2, not Group 19 or Group 14).

    Expected values verified two ways for this exact capture: (1) hand-decoding
    the raw SA payload bytes per RFC 7296 Section 3.3 - 4 transforms present
    (Encryption id=3/ENCR_3DES, no Key Length attribute since 3DES has a
    fixed key size; Integrity id=2/AUTH_HMAC_SHA1_96; PRF id=2/PRF_HMAC_SHA1;
    DH id=2/MODP_1024) - and (2) the live `swanctl --list-sas` output at
    capture time reporting the negotiated proposal as
    "3DES_CBC/HMAC_SHA1_96/PRF_HMAC_SHA1/MODP_1024". Both agree exactly; the
    parser needed no fixes for this proposal shape either.
    """
    assert os.path.exists(WEAK_LEGACY_IKE_PCAP), f"Missing test fixture: {WEAK_LEGACY_IKE_PCAP}"

    res = IKEParser(WEAK_LEGACY_IKE_PCAP).parse()

    assert res["ike_version"] == "IKEv2"
    assert "3DES" in res["encryption_algorithm"]
    assert "SHA1" in res["integrity_algorithm"]
    assert "SHA1" in res["prf_algorithm"]
    assert "MODP_1024" in res["dh_group"]
    assert res["mode"] == "UNKNOWN"
    assert res["pfs"] is False


# =======================================================
# 4. Tests for the Tunnel-vs-Transport ESP payload-length signal
#
# Mode itself is genuinely unobservable in cleartext (see the assertion
# above: IKEParser correctly reports "UNKNOWN"). These tests cover a
# SEPARATE, statistical signal instead: Tunnel mode ESP-encrypts the
# entire original IP packet (own IP header included) before the outer
# header is added; Transport mode does not - so the ESP ciphertext is
# structurally larger in Tunnel mode by roughly the inner IP header size,
# modulo cipher padding and MTU effects. See feature_extractor.py's and
# train_mode_classifier.py's docstrings for the full derivation and honest
# evaluation (leave-one-variant-out balanced accuracy ~0.55 on this
# project's real testbed data - close to chance, NOT presented as reliable).
# =======================================================
TUNNEL_ICMP_PCAP = os.path.join(FIXTURE_DIR, "real_esp_tunnel_icmp.pcap")
TRANSPORT_ICMP_PCAP = os.path.join(FIXTURE_DIR, "real_esp_transport_icmp.pcap")
TUNNEL_VOIP_PCAP = os.path.join(FIXTURE_DIR, "real_esp_tunnel_voip.pcap")
TRANSPORT_VOIP_PCAP = os.path.join(FIXTURE_DIR, "real_esp_transport_voip.pcap")


@pytest.mark.skipif(not SCAPY_INSTALLED, reason="Scapy is not installed in this environment")
def test_esp_payload_length_feature_extraction_real_pcaps():
    """
    Tests that SPLTFeatureExtractor's esp_mean_len/esp_min_len/esp_max_len
    (the ESP ciphertext length, excluding SPI/seq and all outer-header
    bytes - see extract_raw_flows()'s docstring for why this is
    outer-header-agnostic) extracts EXACT, correct values from real
    captures, both tunnel and transport mode, same AES-256-GCM cipher in
    both so the comparison isn't confounded by cipher choice.

    Ground truth verified by hand-decoding the raw bytes (RFC 4303 ESP
    format: SPI(4) + Sequence(4) + payload) directly against
    `pkt[ESP].data`'s length for the first packet of each capture, cross-
    checked against the aggregate stats this session's dataset-wide ESP
    length analysis already established for these exact two files.

    This is the deterministic, always-true part of the mode-inference
    story: the FEATURE is extracted correctly and reproducibly. Whether
    that feature reliably PREDICTS mode when pooled across different
    ciphers and traffic types is the separate, much weaker finding tested
    below (~0.55 balanced accuracy - this is not a general guarantee).
    """
    from ml_pipeline.feature_extractor import SPLTFeatureExtractor

    assert os.path.exists(TUNNEL_ICMP_PCAP), f"Missing test fixture: {TUNNEL_ICMP_PCAP}"
    assert os.path.exists(TRANSPORT_ICMP_PCAP), f"Missing test fixture: {TRANSPORT_ICMP_PCAP}"

    tunnel_extractor = SPLTFeatureExtractor(TUNNEL_ICMP_PCAP, label="icmp", config="tunnel-aes256gcm-ecp256-pfs")
    tunnel_extractor.extract_raw_flows()
    tunnel_flows = tunnel_extractor.compute_features()
    assert len(tunnel_flows) == 1
    # ICMP echo/reply is fixed-size with zero variance (std=0) in this
    # testbed, making it the cleanest possible exact-value assertion.
    assert tunnel_flows[0]["esp_mean_len"] == 112.0
    assert tunnel_flows[0]["esp_std_len"] == 0.0
    assert tunnel_flows[0]["esp_min_len"] == 112
    assert tunnel_flows[0]["esp_max_len"] == 112

    transport_extractor = SPLTFeatureExtractor(TRANSPORT_ICMP_PCAP, label="icmp", config="transport-aes256gcm-ecp256-pfs")
    transport_extractor.extract_raw_flows()
    transport_flows = transport_extractor.compute_features()
    assert len(transport_flows) == 1
    assert transport_flows[0]["esp_mean_len"] == 92.0
    assert transport_flows[0]["esp_std_len"] == 0.0
    assert transport_flows[0]["esp_min_len"] == 92
    assert transport_flows[0]["esp_max_len"] == 92

    # The actual physics: for this SAME cipher (AES-256-GCM), Tunnel mode's
    # ESP payload is exactly 20 bytes larger than Transport mode's - matching
    # RFC 4303's IPv4 inner header size exactly, not just "larger by some
    # padding-dependent amount".
    assert tunnel_flows[0]["esp_mean_len"] - transport_flows[0]["esp_mean_len"] == 20.0


@pytest.mark.skipif(not SCAPY_INSTALLED, reason="Scapy is not installed in this environment")
def test_mode_classifier_correct_on_this_specific_pair():
    """
    Verifies the trained mode_classifier.pkl correctly predicts both
    directions on a real tunnel/transport pair (VoIP traffic, AES-256-GCM
    both sides) - one specific, real, reproducible positive result.

    This is deliberately NOT a claim that the classifier is generally
    reliable - it is measured, honestly, at ~0.55 balanced accuracy (barely
    above the 0.50 chance level) via leave-one-variant-out cross-validation
    across this project's 8 real testbed variants (see
    train_mode_classifier.py). VoIP happens to be one of the traffic types
    where the signal holds up even pooled across variants; ICMP and bulk
    traffic do not (verified separately - ICMP's cipher-dependent overhead
    is of similar magnitude to the tunnel/transport signal itself, and
    bulk's MTU/MSS segmentation effects can invert the direction of the
    size difference entirely). This test documents one real success case,
    not a general reliability guarantee - see mode_inference.reliability
    in main.py's actual API response for how this is honestly surfaced to
    a caller.
    """
    import joblib
    import pandas as pd
    from ml_pipeline.feature_extractor import SPLTFeatureExtractor

    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "mode_classifier.pkl")
    if not os.path.exists(model_path):
        pytest.skip(f"mode_classifier.pkl not found at {model_path} - run train_mode_classifier.py first")
    bundle = joblib.load(model_path)
    clf, features = bundle["model"], bundle["features"]

    assert os.path.exists(TUNNEL_VOIP_PCAP), f"Missing test fixture: {TUNNEL_VOIP_PCAP}"
    assert os.path.exists(TRANSPORT_VOIP_PCAP), f"Missing test fixture: {TRANSPORT_VOIP_PCAP}"

    tunnel_extractor = SPLTFeatureExtractor(TUNNEL_VOIP_PCAP, label="voip", config="tunnel-aes256gcm-ecp256-pfs")
    tunnel_extractor.extract_raw_flows()
    tunnel_flow = tunnel_extractor.compute_features()[0]
    tunnel_pred = clf.predict(pd.DataFrame([tunnel_flow])[features])[0]
    assert tunnel_pred == "tunnel"

    transport_extractor = SPLTFeatureExtractor(TRANSPORT_VOIP_PCAP, label="voip", config="transport-aes256gcm-ecp256-pfs")
    transport_extractor.extract_raw_flows()
    transport_flow = transport_extractor.compute_features()[0]
    transport_pred = clf.predict(pd.DataFrame([transport_flow])[features])[0]
    assert transport_pred == "transport"
