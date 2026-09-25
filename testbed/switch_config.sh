#!/bin/bash
VARIANT=$1
NO_INITIATE=0
if [ "$2" == "--no-initiate" ]; then
    NO_INITIATE=1
fi
if [ -z "$VARIANT" ]; then
    echo "Usage: $0 <variant_name> [--no-initiate]"
    exit 1
fi

if [ ! -f "configs/${VARIANT}-moon.conf" ]; then
    echo "Error: Config configs/${VARIANT}-moon.conf not found!"
    exit 1
fi

mkdir -p configs/active
cp "configs/${VARIANT}-moon.conf" configs/active/moon-swanctl.conf
cp "configs/${VARIANT}-sun.conf" configs/active/sun-swanctl.conf

echo "Switching to $VARIANT..."
# Only restart the gateways to save time. The entrypoint will reload swanctl.
docker compose up -d --force-recreate moon sun

echo "Waiting for charon and tunnels to establish (10s)..."
sleep 10

if [ "$NO_INITIATE" == "1" ]; then
    # Caller (generate_traffic.sh) wants to start a packet capture BEFORE the
    # SA is initiated, so the IKE handshake itself ends up in the pcap. Every
    # capture this testbed produced before this flag existed had 0 IKE packets
    # because this script always initiated before tcpdump could even start.
    echo "Skipping initiate (--no-initiate); connection is loaded, not yet up."
    exit 0
fi

# Initiate the connection from moon to ensure SA is built
docker compose exec moon swanctl --initiate --child testbed > /dev/null 2>&1
sleep 2

echo "=== SAS LIST for $VARIANT ===" >> test_results.log
docker compose exec moon swanctl --list-sas >> test_results.log
