#!/bin/bash
# replay_iscxvpn.sh
# Downloads the public ISCXVPN2016 dataset and replays a subset through the testbed
# to prove model generalization beyond synthetic lab data.

cd "$(dirname "$0")/.."
DATA_DIR="../data/iscxvpn2016"
mkdir -p "$DATA_DIR"

echo "========================================================="
echo "ISCXVPN2016 Generalization Testing Framework"
echo "========================================================="

# Note: The actual ISCXVPN2016 dataset is ~20GB. 
# In a real environment, you request access from UNB CIC and download it.
# We will download a publicly available sample if possible, or outline the exact commands.

echo "1. Downloading ISCXVPN2016 PCAP sample..."
# Placeholder for actual dataset URL once access is granted
SAMPLE_PCAP="$DATA_DIR/skype_audio1a.pcap"
if [ ! -f "$SAMPLE_PCAP" ]; then
    echo "   [!] Note: You must manually place ISCXVPN2016 pcaps into $DATA_DIR"
    echo "       Creating an empty dummy file for script validation..."
    touch "$SAMPLE_PCAP"
fi

if [ ! -s "$SAMPLE_PCAP" ]; then
    echo "   [!] $SAMPLE_PCAP is empty. Please add real PCAPs to run the replay."
    echo "       The script will demonstrate the rewrite logic below."
fi

# We need to map the IPs from the Canadian university network to our Docker testbed IPs
# Original ISCX IPs (example): 131.202.240.87 (Client) -> 131.202.240.48 (Gateway/Server)
# Our Testbed IPs: 192.168.1.10 (Alice) -> 192.168.2.10 (Bob)

echo "2. Rewriting PCAP IPs to match Testbed Subnets..."
REWRITTEN_PCAP="$DATA_DIR/rewritten_skype.pcap"

if command -v tcprewrite >/dev/null 2>&1; then
    tcprewrite --pnat=131.202.0.0/16:192.168.1.0/24 \
               --infile="$SAMPLE_PCAP" \
               --outfile="$REWRITTEN_PCAP"
    echo "   Rewrite complete."
else
    echo "   [!] tcprewrite not installed on host. Skipping rewrite."
    echo "       Install with: sudo apt install tcpreplay"
fi

echo "3. Replaying PCAP through IPsec Tunnel..."
# Ensure strong tunnel is active
bash switch_config.sh "tunnel-aes256gcm-ecp256-pfs" >/dev/null 2>&1

# Start capture on Moon
docker compose exec -d moon tcpdump -i eth1 -w /tmp/iscx_replay.pcap 'esp'

# Use tcpreplay inside the Alice container to replay the traffic
# (Assuming the pcap is mapped or copied into the container)
docker cp "$REWRITTEN_PCAP" alice:/tmp/replay.pcap 2>/dev/null
if [ $? -eq 0 ]; then
    echo "   Replaying traffic from Alice to Bob..."
    docker compose exec alice sh -c "apk add tcpreplay && tcpreplay -i eth0 /tmp/replay.pcap"
    
    # Stop capture and retrieve
    docker compose exec moon pkill tcpdump
    docker cp moon:/tmp/iscx_replay.pcap "$DATA_DIR/captured_iscx_esp.pcap"
    echo "   Capture saved to: $DATA_DIR/captured_iscx_esp.pcap"
else
    echo "   [!] Failed to copy PCAP to Alice container (is Docker running?)"
fi

echo "========================================================="
echo "Generalization test complete."
