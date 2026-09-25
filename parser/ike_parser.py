import struct
import logging
import traceback
try:
    from scapy.all import rdpcap, ISAKMP, UDP, IPv6, IP
    from scapy.packet import NoPayload
except ImportError:
    pass # Handled in execution environments missing Scapy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# IKEv2 payload type numbers (RFC 7296 Section 3.2 / IANA registry)
PAYLOAD_SA = 33

# Transform Type values (RFC 7296 Section 3.3.2)
TRANSFORM_TYPE_ENCR = 1
TRANSFORM_TYPE_PRF = 2
TRANSFORM_TYPE_INTEG = 3
TRANSFORM_TYPE_DH = 4

# Transform IDs we recognize per type (IANA "Transform Type N" registries).
# Names are chosen to match what parser/nist_rules.json and rule_engine.py
# already expect (e.g. "AES-GCM-256", "MODP_2048", "SHA256").
ENCR_NAMES = {
    2: "DES", 3: "3DES",
    12: "AES-CBC", 13: "AES-CTR",
    18: "AES-GCM", 19: "AES-GCM", 20: "AES-GCM",  # ICV length (8/12/16) doesn't change the cipher family
    28: "CHACHA20-POLY1305",
}
PRF_NAMES = {1: "MD5", 2: "SHA1", 5: "SHA256", 6: "SHA384", 7: "SHA512"}
INTEG_NAMES = {1: "MD5", 2: "SHA1", 12: "SHA256", 13: "SHA384", 14: "SHA512"}
DH_NAMES = {
    1: "MODP_768", 2: "MODP_1024", 5: "MODP_1536",
    14: "MODP_2048", 15: "MODP_3072", 16: "MODP_4096",
    19: "ECP_256", 20: "ECP_384", 21: "ECP_521",
    31: "Curve25519",
}


class IKEParser:
    """
    Deterministic parser for IKEv1/IKEv2 packets using Scapy.

    Extracts IKE version and the IKE_SA's own negotiated proposal (encryption/
    PRF/integrity/DH group) from the cleartext IKE_SA_INIT exchange, by
    directly parsing the raw IKEv2 SA/Proposal/Transform binary structure
    (RFC 7296 Section 3.3) - not by string-matching Scapy's text dump.

    IMPORTANT, verified against a real capture (not assumed): Scapy's default
    ISAKMP dissector does NOT decode SA/Proposal/Transform payloads into
    human-readable field names at all - `pkt.show(dump=True)` only ever shows
    the outer payload header (next_payload/length) plus the payload body as a
    raw, sometimes-mis-encoded byte blob. The previous version of this parser
    searched that text dump for literal substrings like "AES_GCM_16_256" or
    "Group 19", which never actually appear anywhere in real Scapy output -
    it only ever "worked" against a hand-written mock string in the test
    suite that happened to contain exactly those substrings.

    `mode` (Tunnel/Transport) and `pfs` are intentionally NOT extracted here
    and are always returned as "UNKNOWN"/False: both are negotiated inside
    the IKE_AUTH or CREATE_CHILD_SA exchange, which is encrypted (wrapped in
    an SK payload) as soon as the IKE_SA exists. A passive observer without
    the derived keys cannot see them - this is a protocol-level constraint,
    not something a better parser can work around. (This matches the
    "Protocol Visibility Limits" already documented in research_dossier.md:
    ESP cipher/mode "must be inferred via ML or read from a gateway config
    file.") Callers should treat `mode`/`pfs` as genuinely unknown, not as a
    confirmed "Transport mode" / "PFS disabled" finding.
    """
    def __init__(self, pcap_path: str):
        self.pcap_path = pcap_path

    def parse(self) -> dict:
        results = {
            "ike_version": "UNKNOWN",
            "encryption_algorithm": [],
            "integrity_algorithm": [],
            "prf_algorithm": [],
            "dh_group": [],
            "pfs": False,
            "mode": "UNKNOWN",
        }

        try:
            packets = rdpcap(self.pcap_path)
            for pkt in packets:
                if ISAKMP not in pkt:
                    continue

                isakmp = pkt[ISAKMP]

                ver = isakmp.version
                if ver == 0x10 or ver == 16:
                    results["ike_version"] = "IKEv1"
                elif ver == 0x20 or ver == 32:
                    results["ike_version"] = "IKEv2"

                for payload_type, raw in self._walk_payloads(isakmp):
                    if payload_type == PAYLOAD_SA:
                        self._parse_sa_payload(raw, results)

        except Exception as e:
            logger.error(f"Error parsing IKE packets with Scapy: {e}")
            logger.error(traceback.format_exc())

        return results

    def _walk_payloads(self, isakmp):
        """
        Yields (payload_type, raw_body_bytes) for each payload chained after
        the ISAKMP header, using the real bytes Scapy stored (`.load`), not
        its text rendering. Scapy gives every payload the same generic
        `ISAKMP_payload` class regardless of type - the type of each one is
        only known from the *previous* payload's (or the header's) own
        `next_payload` field, so the type has to be tracked while walking.
        """
        current_type = isakmp.next_payload
        current = isakmp.payload
        while current is not None and not isinstance(current, NoPayload) and current_type not in (0, None):
            raw = bytes(getattr(current, "load", b""))
            yield current_type, raw
            current_type = getattr(current, "next_payload", 0)
            current = current.payload

    def _parse_sa_payload(self, raw: bytes, results: dict):
        """
        Parses an IKEv2 Security Association payload body (RFC 7296 Section
        3.3): one or more Proposal Substructures, each containing one or more
        Transform Substructures. Verified byte-for-byte against a real
        captured IKE_SA_INIT proposal (AES_GCM_16 transform ID 20 + a Key
        Length attribute of 256 -> "AES-GCM-256"; PRF ID 5 -> "SHA256"; DH
        transform ID 19 -> "ECP_256" - matches exactly what swanctl logged as
        the negotiated proposal for that same handshake).
        """
        offset = 0
        while offset + 8 <= len(raw):
            prop_len = struct.unpack(">H", raw[offset + 2:offset + 4])[0]
            spi_size = raw[offset + 6]
            num_transforms = raw[offset + 7]
            if prop_len <= 0:
                break

            t_off = offset + 8 + spi_size
            prop_end = offset + prop_len
            for _ in range(num_transforms):
                if t_off + 8 > len(raw):
                    break
                t_len = struct.unpack(">H", raw[t_off + 2:t_off + 4])[0]
                if t_len < 8:
                    break
                t_type = raw[t_off + 4]
                t_id = struct.unpack(">H", raw[t_off + 6:t_off + 8])[0]
                key_len = self._parse_key_length_attr(raw, t_off + 8, t_off + t_len)
                self._record_transform(results, t_type, t_id, key_len)
                t_off += t_len

            offset = prop_end if prop_end > offset else len(raw)

    def _parse_key_length_attr(self, raw: bytes, start: int, end: int):
        """Looks for a Key Length transform attribute (type 14, TV format) to
        distinguish e.g. AES-128 from AES-256 - the Transform ID alone
        doesn't encode key size for AES."""
        off = start
        while off + 4 <= end:
            attr_header = struct.unpack(">H", raw[off:off + 2])[0]
            is_tv = bool(attr_header & 0x8000)
            attr_type = attr_header & 0x7FFF
            if is_tv:
                attr_val = struct.unpack(">H", raw[off + 2:off + 4])[0]
                if attr_type == 14:  # Key Length
                    return attr_val
                off += 4
            else:
                if off + 4 > end:
                    break
                attr_len = struct.unpack(">H", raw[off + 2:off + 4])[0]
                off += 4 + attr_len
        return None

    def _record_transform(self, results: dict, t_type: int, t_id: int, key_len):
        if t_type == TRANSFORM_TYPE_ENCR:
            name = ENCR_NAMES.get(t_id)
            if name and name in ("AES-CBC", "AES-GCM"):
                bits = key_len if key_len else 128
                self._add_unique(results["encryption_algorithm"], f"{name}-{bits}")
            elif name:
                self._add_unique(results["encryption_algorithm"], name)
        elif t_type == TRANSFORM_TYPE_PRF:
            name = PRF_NAMES.get(t_id)
            if name:
                self._add_unique(results["prf_algorithm"], name)
        elif t_type == TRANSFORM_TYPE_INTEG:
            name = INTEG_NAMES.get(t_id)
            if name:
                self._add_unique(results["integrity_algorithm"], name)
        elif t_type == TRANSFORM_TYPE_DH:
            name = DH_NAMES.get(t_id)
            if name:
                self._add_unique(results["dh_group"], name)

    def _add_unique(self, lst: list, item: str):
        if item not in lst:
            lst.append(item)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        parser = IKEParser(sys.argv[1])
        print(parser.parse())
