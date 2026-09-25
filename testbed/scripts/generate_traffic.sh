#!/bin/bash
# generate_traffic.sh
# Generates and captures labeled traffic (VoIP, Web, Video, Email, ICMP, Bulk)
# across all IPsec configuration variants.

cd "$(dirname "$0")/.."

DATA_DIR="../data/raw"
MANIFEST="$DATA_DIR/dataset_manifest.csv"
mkdir -p "$DATA_DIR"

# Initialize manifest
if [ ! -f "$MANIFEST" ]; then
    echo "pcap_filename,config_variant,traffic_class,duration_sec" > "$MANIFEST"
fi

VARIANTS=(
    "tunnel-aes256gcm-ecp256-pfs"
    "tunnel-aes128cbc-sha256-modp2048-pfs"
    "tunnel-aes256cbc-sha1-modp2048-nopfs"
    "tunnel-aes128gcm-curve25519-pfs"
    "transport-aes256gcm-ecp256-pfs"
    "transport-aes128cbc-sha256-modp2048-pfs"
    "tunnel-weak-3des-sha1-modp1024"
    "tunnel-aes256gcm-ecp256-pfs-ipv6"
)

TRAFFIC_TYPES=("icmp" "bulk" "web" "video" "voip" "email")
CAPTURE_DUR=15

echo "Ensuring infrastructure is up..."
docker compose up -d alice bob

# Setup servers on Bob (used for TUNNEL mode variants: alice -> bob traffic
# actually flows through the tunnel).
echo "Setting up servers on Bob..."
docker compose exec -d bob sh -c "mkdir -p /www && dd if=/dev/urandom of=/www/10MB.bin bs=1M count=10 >/dev/null 2>&1"
docker compose exec -d bob sh -c "cd /www && python3 -m http.server 80 >/dev/null 2>&1"
# Separate IPv6 instance on its own port: verified directly that on this
# Alpine/musl environment, binding a single http.server to "::" is
# IPv6-ONLY (unlike glibc's usual dual-stack default) - it does NOT also
# accept IPv4 connections. Running two instances on different ports avoids
# breaking IPv4 (used by 7 of the 8 variants) while still supporting the
# one IPv6 variant.
docker compose exec -d bob sh -c "cd /www && python3 -m http.server 8080 --bind :: >/dev/null 2>&1"
docker compose exec -d bob sh -c "iperf3 -s >/dev/null 2>&1"
docker compose exec -d bob sh -c "nc -l -p 25 >/dev/null 2>&1" # Stub for Email (SMTP)
sleep 2

setup_sun_servers() {
    # Same servers as Bob, but for Sun - used for TRANSPORT mode variants.
    # Real finding this session: Transport mode's SA only ever protects
    # traffic whose IP src/dst are the two IPsec endpoints THEMSELVES
    # (moon<->sun) - it cannot protect alice->bob traffic transiting through
    # the gateways. Verified directly: `swanctl --list-sas` showed a
    # genuinely ESTABLISHED transport SA with 0 bytes/0 packets transferred
    # after 200+ seconds of alice pinging bob. For transport-mode variants,
    # traffic must originate FROM moon and go TO sun directly, so it needs
    # its own servers (moon/sun's image now includes iperf3/curl/python3,
    # added specifically for this).
    #
    # MUST be called AFTER switch_config.sh for each transport variant, not
    # once up front: switch_config.sh force-recreates sun to load its new
    # swanctl config, which wipes out any background servers started before
    # that recreate. Found by testing: icmp (no server needed, just the
    # kernel's ICMP responder) worked fine, but bulk/video/voip/web/email
    # (all needing a listener on sun) each produced only a single failed
    # 2-packet connection attempt - because the real iperf3/http.server/nc
    # processes were already dead, killed by the recreate.
    docker compose exec -d sun sh -c "mkdir -p /www && dd if=/dev/urandom of=/www/10MB.bin bs=1M count=10 >/dev/null 2>&1"
    docker compose exec -d sun sh -c "cd /www && python3 -m http.server 80 >/dev/null 2>&1"
    docker compose exec -d sun sh -c "iperf3 -s >/dev/null 2>&1"
    docker compose exec -d sun sh -c "nc -l -p 25 >/dev/null 2>&1"
    sleep 2
}

generate_traffic() {
    local t_type=$1
    local target_ip=$2
    local src_container=$3
    echo "Generating $t_type traffic from $src_container to $target_ip for $CAPTURE_DUR seconds..."

    case $t_type in
        "icmp")
            docker compose exec $src_container ping -i 0.5 -c $((CAPTURE_DUR*2)) $target_ip >/dev/null 2>&1
            ;;
        "bulk")
            # Capped at 10Mbps. Uncapped TCP iperf3 saturated the Docker bridge
            # and produced a 184MB pcap in 15s, which crashed the Docker daemon
            # by filling its WSL2 VM disk mid-write. 10Mbps for 15s (~18MB) is
            # still a genuine sustained bulk-transfer shape - the ML features
            # are per-flow aggregate stats, not raw byte counts, so this loses
            # no real training signal while being ~10x smaller across 8 variants.
            docker compose exec $src_container iperf3 -c $target_ip -t $CAPTURE_DUR -b 10M >/dev/null 2>&1
            ;;
        "video")
            # Video: UDP, high bandwidth, variable bursts. Mimic 5Mbps stream
            # Use iperf3's own -t so it terminates itself; backgrounding + `kill $!`
            # only killed the local `docker compose exec` client, not the remote
            # iperf3 process, which could bleed into the next capture window.
            docker compose exec $src_container iperf3 -c $target_ip -u -b 5M -t $CAPTURE_DUR >/dev/null 2>&1
            ;;
        "voip")
            # VoIP: UDP, very low bandwidth, highly periodic small packets (160 bytes, 20ms = ~64Kbps)
            docker compose exec $src_container iperf3 -c $target_ip -u -b 64K -l 160 -t $CAPTURE_DUR >/dev/null 2>&1
            ;;
        "web")
            # Web: Fetch files via HTTP with random pauses.
            # IPv6 literals need brackets in a URL (host:port syntax would
            # otherwise be ambiguous with the address's own colons). Verified
            # directly: curl rejected "http://fd02::10/..." outright with
            # "URL rejected: Port number was not a decimal number" and only
            # accepted "http://[fd02::10]/...". This is why the ipv6 variant's
            # web.pcap was empty (24 bytes) even though icmp/bulk/video/voip
            # all worked fine (iperf3/ping take the target as a plain
            # argument, not part of a URL, so they never hit this ambiguity).
            # Also: the IPv6 http.server instance runs on its own port 8080,
            # not 80 - verified directly that on this Alpine/musl environment
            # binding to "::" is IPv6-ONLY (not dual-stack), so a single
            # server can't serve both families on one port here.
            local http_target="$target_ip"
            local http_port="80"
            if [[ "$target_ip" == *:* ]]; then
                http_target="[$target_ip]"
                http_port="8080"
            fi
            for i in $(seq 1 5); do
                docker compose exec $src_container curl -s http://$http_target:$http_port/10MB.bin -o /dev/null
                sleep 2
            done
            ;;
        "email")
            # Email: Short TCP bursts simulating SMTP/IMAP emails with attachments
            for i in $(seq 1 3); do
                docker compose exec $src_container iperf3 -c $target_ip -n 50K >/dev/null 2>&1
                sleep 3
            done
            ;;
    esac
}

for v in "${VARIANTS[@]}"; do
    echo "=========================================="
    echo "Generating dataset for config: $v"

    # Resumable: skip variants whose full set of expected captures already
    # exists on disk (all real, non-empty). Lets a run be safely re-invoked
    # after a partial failure without redoing already-verified variants.
    ALREADY_DONE=1
    for t in "ike_handshake" "${TRAFFIC_TYPES[@]}"; do
        f="$DATA_DIR/${v}_${t}.pcap"
        # >100 bytes, not just non-empty: a pcap with a valid header but zero
        # captured packets is ~24 bytes and must NOT count as "done" - this is
        # exactly the shape of the empty transport-mode captures found this
        # session (real file, valid pcap format, zero actual packets).
        size=$(stat -c%s "$f" 2>/dev/null || echo 0)
        if [ "$size" -le 100 ]; then
            ALREADY_DONE=0
            break
        fi
    done
    if [ "$ALREADY_DONE" == "1" ]; then
        echo "Skipping $v - all captures already present and non-empty."
        continue
    fi

    # Bring the gateways up WITHOUT initiating yet, so we can start tcpdump
    # first and actually capture the IKE handshake. Every prior pcap this
    # testbed produced had 0 IKE packets because the old switch_config.sh
    # always initiated the SA before capture could start.
    bash switch_config.sh "$v" --no-initiate

    if [[ "$v" == transport-* ]]; then
        setup_sun_servers
    fi

    # Transport mode can only ever protect traffic between the two IPsec
    # endpoints themselves (moon<->sun), not traffic transiting through them
    # from alice/bob - see the comment above the sun server setup for the
    # verified reason. So transport-mode variants generate traffic FROM moon
    # TO sun directly; tunnel-mode variants keep using alice -> bob as before.
    if [[ "$v" == transport-* ]]; then
        SRC_CONTAINER="moon"
        TARGET_IP="10.0.0.2"
    else
        SRC_CONTAINER="alice"
        TARGET_IP="192.168.2.10"
        if [[ "$v" == *"ipv6"* ]]; then
            TARGET_IP="fd02::10"
        fi
    fi

    IKE_PCAP="${v}_ike_handshake.pcap"
    echo "--> Capturing: $IKE_PCAP"
    WAN_IF=$(docker compose exec moon sh -c "ip -o -4 addr show | grep '10\.0\.0\.' | awk '{print \$2}'" | tr -d '\r')
    if [ -z "$WAN_IF" ]; then
        echo "ERROR: could not detect moon's WAN interface, skipping $v entirely"
        continue
    fi
    docker compose exec -d moon tcpdump -i "$WAN_IF" -w /tmp/$IKE_PCAP 'esp or udp port 500 or udp port 4500'
    sleep 1

    # Now actually initiate - this is what generates the IKE_SA_INIT/IKE_AUTH
    # exchange that the tcpdump above is now positioned to catch.
    docker compose exec moon swanctl --initiate --child testbed > /dev/null 2>&1
    sleep 3

    docker compose exec moon pkill tcpdump
    sleep 1
    docker cp moon:/tmp/$IKE_PCAP "$DATA_DIR/$IKE_PCAP"
    docker compose exec moon rm -f /tmp/$IKE_PCAP
    echo "$IKE_PCAP,$v,ike_handshake,4" >> "$MANIFEST"

    echo "=== SAS LIST for $v ===" >> test_results.log
    docker compose exec moon swanctl --list-sas >> test_results.log

    sleep 2 # Wait for tunnel stabilization before traffic-type captures

    for t in "${TRAFFIC_TYPES[@]}"; do
        PCAP_NAME="${v}_${t}.pcap"
        echo "--> Capturing: $PCAP_NAME"
        
        # Start capture on Moon (WAN link). Capture IKE (500/4500) and ESP (50)
        # Interface names are NOT consistent across containers (verified: on moon
        # eth0 is WAN/10.0.0.0-24 while on sun eth1 is WAN instead) so the WAN
        # interface must be detected by IP match, not assumed by name.
        WAN_IF=$(docker compose exec moon sh -c "ip -o -4 addr show | grep '10\.0\.0\.' | awk '{print \$2}'" | tr -d '\r')
        if [ -z "$WAN_IF" ]; then
            echo "ERROR: could not detect moon's WAN interface, skipping $PCAP_NAME"
            continue
        fi
        docker compose exec -d moon tcpdump -i "$WAN_IF" -w /tmp/$PCAP_NAME 'esp or udp port 500 or udp port 4500'

        # Give tcpdump a second to initialize
        sleep 1

        # Generate the traffic
        generate_traffic "$t" "$TARGET_IP" "$SRC_CONTAINER"
        
        # Stop capture
        docker compose exec moon pkill tcpdump
        sleep 1
        
        # Extract PCAP from container
        docker cp moon:/tmp/$PCAP_NAME "$DATA_DIR/$PCAP_NAME"
        docker compose exec moon rm /tmp/$PCAP_NAME
        
        # Append to manifest
        echo "$PCAP_NAME,$v,$t,$CAPTURE_DUR" >> "$MANIFEST"
        
    done
done

echo "=========================================="
echo "Traffic generation complete."
echo "Manifest saved to: $MANIFEST"
echo "Total PCAPs: $(cat $MANIFEST | wc -l) (includes header)"
