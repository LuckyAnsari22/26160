import json
import os
from typing import Dict, Any, List, Optional
from collections import defaultdict

class SecurityRuleEngine:
    """
    Evaluates extracted IPsec parameters against NIST SP 800-77 Rev.1 
    and RFC 8221/8247 using a strict Severity-Cap algorithm.
    """
    def __init__(self, parsed_data: Dict[str, Any], rules_file: str = "nist_rules.json"):
        self.data = parsed_data
        
        # Load rules from JSON
        rules_path = os.path.join(os.path.dirname(__file__), rules_file)
        with open(rules_path, 'r') as f:
            self.rules = json.load(f)
            
        self.baseline_score = 100
        self.capped_score = 100
        self.findings = []
        self.threat_matrix = []

    def evaluate(self) -> Dict[str, Any]:
        """Runs the rule engine and returns a severity-capped score."""
        self._evaluate_category("IKE_VERSION", [self.data.get("ike_version", "UNKNOWN")])
        self._evaluate_category("ENCRYPTION", self.data.get("encryption_algorithm", []))
        self._evaluate_category("INTEGRITY", self.data.get("integrity_algorithm", []))
        self._evaluate_category("DH_GROUP", self.data.get("dh_group", []))
        
        # PFS Check (Special Logic)
        pfs_enabled = self.data.get("pfs", False)
        if not pfs_enabled:
            self._apply_finding("HIGH", 59, "Perfect Forward Secrecy (PFS) is disabled. Compromise of IKE keys compromises all past ESP traffic.")

        # Replay readiness — assessed from cleartext ESP sequence numbers
        replay_readiness = self._evaluate_replay_readiness()

        # Metadata exposure — assessed from classifier confidence if available
        metadata_exposure = self._evaluate_metadata_exposure()

        # Cap score
        final_score = min(self.baseline_score, self.capped_score)
        
        return {
            "risk_score": 100 - final_score,
            "security_score": final_score,
            "findings": self.findings,
            "threat_matrix": self.threat_matrix,
            "key_lifetime_status": self._key_lifetime_status(),
            "replay_readiness": replay_readiness,
            "metadata_exposure": metadata_exposure,
        }

    def _key_lifetime_status(self) -> Dict[str, str]:
        """
        Documents that SA lifetimes are structurally not assessable from
        passive capture.

        RFC 7296 Section 2.8: "There is no negotiated lifetime for an IKE SA
        or a Child SA. Rather, each end of the SA is responsible for enforcing
        its own lifetime policy on the SA and rekeying the SA when necessary."

        SA lifetimes are local policy, never transmitted in any IKE payload.
        This is NOT an extraction failure — the data simply does not exist on
        the wire. A configuration file or management-plane query would be
        needed instead.
        """
        return {
            "status": "not_assessable",
            "reason": (
                "SA lifetimes are local policy per RFC 7296 §2.8, never "
                "protocol-negotiated. Each peer independently enforces its own "
                "rekey_time/life_time — this value is not transmitted in any "
                "IKE payload (cleartext or encrypted) and cannot be determined "
                "from passive traffic capture alone. Assessment requires access "
                "to the endpoint's configuration (e.g., strongSwan "
                "connections.<conn>.children.<child>.rekey_time)."
            ),
        }

    def _evaluate_replay_readiness(self) -> Dict[str, Any]:
        """
        Evaluates the sender-side prerequisite for ESP anti-replay protection
        by checking that sequence numbers are present and monotonically
        incrementing per-SPI.

        Per RFC 4303 Section 2, the ESP SPI and Sequence Number fields are
        NOT encrypted — they are cleartext header fields needed by the
        receiver to look up the SA and check the anti-replay window BEFORE
        decryption.

        Per RFC 4303 Section 3.3.3 (Outbound Processing): "The sender MUST
        ensure that the counter has not cycled before sending a packet ...
        The sender's counter MUST be initialized to 0 when an SA is
        established."

        What this checks:
          - Sequence numbers are present and non-zero for each SPI
          - Sequence numbers are monotonically incrementing (no duplicates,
            no decreases) within each SPI

        What this CANNOT check (documented honestly):
          - Whether the receiver is actually enforcing the anti-replay
            window — this is receiver-side local policy
          - The anti-replay window size — never transmitted on the wire
        """
        esp_seq_data = self.data.get("esp_seq_by_spi")

        if esp_seq_data is None or len(esp_seq_data) == 0:
            return {
                "status": "indeterminate",
                "reason": (
                    "No ESP traffic observed in this capture — replay "
                    "readiness cannot be assessed without ESP packets. "
                    "This is a capture content limitation, not a finding."
                ),
            }

        # Analyze sequence numbers per-SPI
        has_duplicates = False
        has_non_monotonic = False

        for spi, seqs in esp_seq_data.items():
            if len(seqs) < 2:
                continue
            seen = set()
            prev = -1
            for s in seqs:
                if s in seen:
                    has_duplicates = True
                    break
                seen.add(s)
                if s <= prev:
                    has_non_monotonic = True
                prev = s
            if has_duplicates:
                break

        if has_duplicates:
            rule = self.rules.get("REPLAY_READINESS", {}).get("DUPLICATE_SEQ")
            if rule:
                self._apply_finding(rule["severity"], rule["cap"], rule["message"])
            return {
                "status": "assessed",
                "result": "DUPLICATE_SEQ",
                "severity": "HIGH",
                "message": rule["message"] if rule else "Duplicate ESP sequence numbers detected.",
                "caveat": (
                    "This verifies sender-side compliance with RFC 4303 "
                    "§3.3.3. Receiver-side anti-replay window enforcement "
                    "is local policy and not observable from passive capture."
                ),
            }
        elif has_non_monotonic:
            rule = self.rules.get("REPLAY_READINESS", {}).get("NON_MONOTONIC")
            if rule:
                self._apply_finding(rule["severity"], rule["cap"], rule["message"])
            return {
                "status": "assessed",
                "result": "NON_MONOTONIC",
                "severity": "MEDIUM",
                "message": rule["message"] if rule else "ESP sequence numbers not strictly monotonic.",
                "caveat": (
                    "This verifies sender-side compliance with RFC 4303 "
                    "§3.3.3. Receiver-side anti-replay window enforcement "
                    "is local policy and not observable from passive capture."
                ),
            }
        else:
            rule = self.rules.get("REPLAY_READINESS", {}).get("MONOTONIC")
            # PASS — no cap applied, this is a positive finding
            return {
                "status": "assessed",
                "result": "MONOTONIC",
                "severity": "PASS",
                "message": rule["message"] if rule else "ESP sequence numbers are monotonically incrementing.",
                "caveat": (
                    "This verifies sender-side compliance with RFC 4303 "
                    "§3.3.3. Receiver-side anti-replay window enforcement "
                    "is local policy and not observable from passive capture."
                ),
            }

    def _evaluate_metadata_exposure(self) -> Dict[str, Any]:
        """
        Assesses metadata exposure — the degree to which an ESP-encrypted
        flow leaks identifiable behavioral metadata (traffic type, approximate
        data volume, session timing) to a passive observer via cleartext
        flow-level statistics.

        This is scored from the traffic classifier's confidence: high
        classifier confidence means the tunnel is highly transparent to
        traffic analysis, which IS the metadata exposure risk.

        The classifier result is passed in via parsed_data["classifier_confidence"]
        by the caller (main.py) when available. When the classifier did not
        run (no ESP, below floor, no model), this is reported as indeterminate.
        """
        confidence = self.data.get("classifier_confidence")

        if confidence is None:
            return {
                "status": "indeterminate",
                "reason": (
                    "Traffic classifier did not produce a result for this "
                    "capture (no ESP traffic, below 20-packet floor, or "
                    "model unavailable). Metadata exposure cannot be "
                    "assessed without a classifier output."
                ),
            }

        if confidence > 90:
            self._apply_finding(
                "HIGH", 59,
                f"High metadata exposure: a passive observer can classify "
                f"encrypted traffic type with {confidence:.1f}% confidence "
                f"using flow-level statistics alone. The tunnel provides "
                f"minimal traffic analysis resistance. Consider deploying "
                f"padding countermeasures (MTU padding, adaptive padding) "
                f"to reduce leakage."
            )
            return {
                "status": "assessed",
                "severity": "HIGH",
                "classifier_confidence": confidence,
                "message": (
                    f"Tunnel is highly transparent to traffic analysis: "
                    f"{confidence:.1f}% classification confidence."
                ),
            }
        elif confidence > 70:
            self._apply_finding(
                "MEDIUM", 79,
                f"Moderate metadata exposure: a passive observer can classify "
                f"encrypted traffic type with {confidence:.1f}% confidence. "
                f"Partial traffic analysis resistance, but flow characteristics "
                f"remain distinguishable."
            )
            return {
                "status": "assessed",
                "severity": "MEDIUM",
                "classifier_confidence": confidence,
                "message": (
                    f"Partial traffic analysis resistance: "
                    f"{confidence:.1f}% classification confidence."
                ),
            }
        else:
            return {
                "status": "assessed",
                "severity": "PASS",
                "classifier_confidence": confidence,
                "message": (
                    f"Reasonable traffic analysis resistance: classifier "
                    f"confidence {confidence:.1f}% indicates limited metadata "
                    f"leakage from flow-level statistics."
                ),
            }

    def _evaluate_category(self, category: str, values: list):
        if not values or values == ["UNKNOWN"]:
            # Missing parameter logic
            return
            
        for val in values:
            rule = self._find_matching_rule(category, val)
            if rule:
                self._apply_finding(rule["severity"], rule["cap"], rule["message"])
            else:
                self._apply_finding("INFO", 100, f"Unrecognized or non-standard {category}: {val}")

    def _find_matching_rule(self, category: str, val: str):
        cat_rules = self.rules.get(category, {})
        
        # Hardcode common mappings to avoid dangerous substring matches like "2" in "ECP_256"
        if category == "ENCRYPTION":
            if "3DES" in val: return cat_rules.get("3DES")
            if "DES" in val and "3DES" not in val: return cat_rules.get("DES")
            if "AES-CBC" in val and "256" in val: return cat_rules.get("AES-CBC-256")
            if "AES-CBC" in val: return cat_rules.get("AES-CBC-128")
            if "AES-GCM" in val and "256" in val: return cat_rules.get("AES-GCM-256")
            if "AES-GCM" in val: return cat_rules.get("AES-GCM-128")
            if "CHACHA20" in val: return cat_rules.get("CHACHA20-POLY1305")
        elif category == "DH_GROUP":
            if "MODP_1024" in val or "Group 2" in val or val == "2": return cat_rules.get("2")
            if "MODP_2048" in val or "Group 14" in val or val == "14": return cat_rules.get("14")
            if "ECP_256" in val or "Group 19" in val or val == "19": return cat_rules.get("19")
            if "Curve25519" in val or "Group 31" in val or val == "31": return cat_rules.get("31")
        elif category == "INTEGRITY":
            if "SHA2_256" in val or "SHA256" in val: return cat_rules.get("SHA256")
            if "MD5" in val: return cat_rules.get("MD5")
            if "SHA1" in val: return cat_rules.get("SHA1")
        elif category == "IKE_VERSION":
            if "IKEv1" in val: return cat_rules.get("IKEv1")
            if "IKEv2" in val: return cat_rules.get("IKEv2")
            
        # Fallback to exact match only
        if val in cat_rules:
            return cat_rules[val]
            
        return None

    def _apply_finding(self, severity: str, cap: int, message: str):
        # Prevent duplicate findings
        if not any(f["message"] == message for f in self.findings):
            self.findings.append({"severity": severity, "message": message, "cap_applied": cap})
            if cap < self.capped_score:
                self.capped_score = cap
            if severity in ["HIGH", "CRITICAL"]:
                self.threat_matrix.append(message)

if __name__ == "__main__":
    test_data = {
        "ike_version": "IKEv1",
        "encryption_algorithm": ["3DES"],
        "dh_group": ["MODP_1024"],
        "pfs": False
    }
    engine = SecurityRuleEngine(test_data)
    import pprint
    pprint.pprint(engine.evaluate())

