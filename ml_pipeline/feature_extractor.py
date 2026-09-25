import os
import csv
import logging
from collections import defaultdict
import numpy as np

try:
    from scapy.all import rdpcap, IP, IPv6, UDP, ESP
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SPLTFeatureExtractor:
    """
    Extracts Sequence of Packet Lengths and Times (SPLT) features from IPsec PCAPs.
    Implements the 20-packet minimum floor rule for encrypted traffic classification.
    """
    def __init__(self, pcap_path: str, label: str, config: str):
        self.pcap_path = pcap_path
        self.label = label
        self.config = config
        self.flows = defaultdict(list)
        
    def _get_flow_key(self, pkt) -> str:
        """
        IPsec flows are keyed by outer IP pair ONLY (no SPI).

        Originally this also included the packet's ESP SPI, but ESP SPIs are
        inherently unidirectional per RFC 4303 - the inbound and outbound legs
        of the SAME tunnel conversation use two different SPIs. Including SPI
        in the key therefore split one genuinely bidirectional conversation
        into two separate unidirectional "flows" (each with direction_ratio
        exactly 1.0), which is the opposite of the bidirectional grouping this
        was meant to do. Confirmed against a real captured pcap: a single
        tunnel produced two flows before this fix, one after.
        """
        src = pkt[IP].src if IP in pkt else pkt[IPv6].src if IPv6 in pkt else "unknown"
        dst = pkt[IP].dst if IP in pkt else pkt[IPv6].dst if IPv6 in pkt else "unknown"

        # Bi-directional flow key: sort IPs so A->B and B->A map to same flow
        ips = sorted([src, dst])
        return f"{ips[0]}_{ips[1]}"

    def extract_raw_flows(self):
        try:
            packets = rdpcap(self.pcap_path)
            for pkt in packets:
                if ESP in pkt or (UDP in pkt and pkt[UDP].dport in [500, 4500]):
                    flow_key = self._get_flow_key(pkt)
                    # Store (timestamp, length, direction(src))
                    src = pkt[IP].src if IP in pkt else pkt[IPv6].src if IPv6 in pkt else "unknown"
                    # ESP-payload (ciphertext) length, for the Tunnel-vs-Transport
                    # structural signal: Tunnel mode ESP-encrypts the entire
                    # original IP packet (its own IP header included) inside the
                    # new outer header; Transport mode only encrypts the original
                    # payload, leaving the original IP header outside ESP in
                    # cleartext. So the ESP ciphertext itself is structurally
                    # larger in Tunnel mode by roughly the inner IP header size
                    # (20B IPv4 / 40B IPv6), modulo cipher block-padding and MTU
                    # segmentation effects. `pkt[ESP].data` is scapy's own
                    # dissection of exactly the ESP payload bytes (SPI/seq
                    # already excluded), and is outer-header-agnostic (unaffected
                    # by outer IPv4 vs IPv6, Ethernet framing, or NAT-T UDP
                    # encapsulation) - verified by hand against real captures.
                    # None for IKE control packets (no ESP layer at all).
                    esp_len = len(pkt[ESP].data) if ESP in pkt else None
                    self.flows[flow_key].append({
                        "time": float(pkt.time),
                        "len": len(pkt),
                        "esp_len": esp_len,
                        "src": src
                    })
        except Exception as e:
            logger.error(f"Failed to read {self.pcap_path}: {e}")

    def compute_features(self) -> list:
        features = []
        for flow_id, pkts in self.flows.items():
            pkt_count = len(pkts)
            
            # --- 20-PACKET FLOOR RULE ---
            if pkt_count < 20:
                logger.debug(f"Flow {flow_id} discarded (Micro-flow: {pkt_count} pkts)")
                continue
                
            pkts = sorted(pkts, key=lambda x: x["time"])
            
            # Directional stats
            initiator_ip = pkts[0]["src"]
            fwd_pkts = [p for p in pkts if p["src"] == initiator_ip]
            bwd_pkts = [p for p in pkts if p["src"] != initiator_ip]
            
            direction_ratio = len(fwd_pkts) / pkt_count if pkt_count > 0 else 0
            
            # Length stats
            lengths = [p["len"] for p in pkts]
            
            # IAT stats
            iats = [pkts[i]["time"] - pkts[i-1]["time"] for i in range(1, len(pkts))]
            if not iats: iats = [0.0]

            # ESP-payload length stats (Tunnel vs Transport structural signal -
            # see extract_raw_flows() for why this is a distinct measurement
            # from mean_len/std_len/etc above, which use the OUTER packet
            # length and are used for traffic-type classification instead).
            # esp_len is None for IKE control packets, which don't carry this
            # signal at all - excluded from these stats rather than treated
            # as zero.
            esp_lengths = [p["esp_len"] for p in pkts if p["esp_len"] is not None]
            if esp_lengths:
                esp_mean_len = np.mean(esp_lengths)
                esp_std_len = np.std(esp_lengths)
                esp_min_len = np.min(esp_lengths)
                esp_max_len = np.max(esp_lengths)
            else:
                esp_mean_len = esp_std_len = esp_min_len = esp_max_len = np.nan

            features.append({
                "flow_id": flow_id,
                "config": self.config,
                "label": self.label,
                "pkt_count": pkt_count,
                "direction_ratio": direction_ratio,
                "mean_len": np.mean(lengths),
                "std_len": np.std(lengths),
                "max_len": np.max(lengths),
                "min_len": np.min(lengths),
                "mean_iat": np.mean(iats),
                "std_iat": np.std(iats),
                "max_iat": np.max(iats),
                "flow_duration": pkts[-1]["time"] - pkts[0]["time"],
                "esp_mean_len": esp_mean_len,
                "esp_std_len": esp_std_len,
                "esp_min_len": esp_min_len,
                "esp_max_len": esp_max_len,
            })
            
        return features

def batch_process(manifest_path: str, output_csv: str):
    all_features = []
    
    if not os.path.exists(manifest_path):
        logger.error("Manifest not found.")
        return
        
    with open(manifest_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pcap = os.path.join(os.path.dirname(manifest_path), row['pcap_filename'])
            if os.path.exists(pcap):
                extractor = SPLTFeatureExtractor(pcap, row['traffic_class'], row['config_variant'])
                extractor.extract_raw_flows()
                all_features.extend(extractor.compute_features())
                
    if all_features:
        keys = all_features[0].keys()
        with open(output_csv, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(all_features)
        logger.info(f"Extracted features for {len(all_features)} flows to {output_csv}")
    else:
        logger.warning("No flows extracted (check 20-packet floor or missing PCAPs).")

if __name__ == "__main__":
    batch_process("../data/raw/dataset_manifest.csv", "../data/features.csv")
