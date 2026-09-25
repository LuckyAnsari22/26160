#!/bin/bash

cd "$(dirname "$0")"

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

echo "Starting tests at $(date)..." > test_results.log
declare -A RESULTS

# Ensure network is up first
docker compose up -d alice bob

for v in "${VARIANTS[@]}"; do
    echo "=========================================="
    echo "Testing $v"
    echo "=========================================="
    
    bash switch_config.sh "$v"
    
    # Check if SA is installed
    SA_STATUS=$(docker compose exec moon swanctl --list-sas)
    if echo "$SA_STATUS" | grep -q "INSTALLED"; then
        SA_ESTABLISHED="YES"
    else
        SA_ESTABLISHED="NO"
    fi
    
    # Check data plane
    if [[ "$v" == *"ipv6"* ]]; then
        docker compose exec alice ping -6 -c 2 -W 2 fd02::10 > /dev/null 2>&1
        PING_RES=$?
    else
        docker compose exec alice ping -c 2 -W 2 192.168.2.10 > /dev/null 2>&1
        PING_RES=$?
    fi
    
    if [ $SA_ESTABLISHED == "YES" ] && [ $PING_RES -eq 0 ]; then
        echo "$v: PASS (SA: UP, Ping: OK)" | tee -a test_results.log
        RESULTS["$v"]="PASS"
    elif [ $SA_ESTABLISHED == "YES" ] && [ $PING_RES -ne 0 ]; then
        echo "$v: PARTIAL (SA: UP, Ping: FAIL)" | tee -a test_results.log
        RESULTS["$v"]="PARTIAL_PING_FAIL"
    else
        echo "$v: FAIL (SA: DOWN)" | tee -a test_results.log
        RESULTS["$v"]="FAIL_SA_DOWN"
    fi
done

echo "=================="
echo "SUMMARY"
echo "=================="
for v in "${VARIANTS[@]}"; do
    printf "%-40s : %s\n" "$v" "${RESULTS[$v]}"
done
