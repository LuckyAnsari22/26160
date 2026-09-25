#!/bin/sh
sysctl -w net.ipv4.ip_forward=1
sysctl -w net.ipv6.conf.all.forwarding=1
/usr/lib/strongswan/charon &
sleep 3
swanctl --load-all
echo "IPsec gateway ready"
tail -f /dev/null
