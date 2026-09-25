#!/bin/bash
# VPN Testbed Setup for IPsec Analysis
# This script sets up a basic strongSwan container for generating test traffic

set -e

echo "Setting up strongSwan testbed..."

# Create strongswan configuration directory
mkdir -p strongswan_config

# 1. Base Configuration (IKEv2, AES-GCM-256, Tunnel mode)
cat <<EOF > strongswan_config/ipsec.conf
config setup
    charondebug="ike 1, knl 1, cfg 0"
    uniqueids=no

conn %default
    ikelifetime=60m
    keylife=20m
    rekeymargin=3m
    keyingtries=1
    keyexchange=ikev2
    authby=secret

conn testbed-gcm
    left=10.0.0.1
    leftsubnet=192.168.1.0/24
    right=10.0.0.2
    rightsubnet=192.168.2.0/24
    ike=aes256gcm16-prfsha256-ecp256!
    esp=aes256gcm16-ecp256!
    auto=start
    type=tunnel
EOF

cat <<EOF > strongswan_config/ipsec.secrets
10.0.0.1 10.0.0.2 : PSK "testbed_preshared_key"
EOF

# 2. Vulnerable Configuration (IKEv1, 3DES, Group 2) for Rule Engine validation
cat <<EOF > strongswan_config/ipsec_weak.conf
config setup
    charondebug="ike 1, knl 1, cfg 0"
    uniqueids=no

conn testbed-weak
    left=10.0.0.1
    leftsubnet=192.168.1.0/24
    right=10.0.0.2
    rightsubnet=192.168.2.0/24
    keyexchange=ikev1
    ike=3des-sha1-modp1024!
    esp=3des-sha1!
    auto=start
    type=tunnel
EOF

echo "To run this testbed, use Docker or LXC with strongSwan installed."
echo "For example:"
echo "  docker run -d --privileged -v \$(pwd)/strongswan_config/ipsec.conf:/etc/ipsec.conf vimagick/strongswan"
echo ""
echo "Use 'tcpdump -i any -w data/capture.pcap udp port 500 or udp port 4500 or esp' to capture the generated traffic."
