FROM alpine:3.19

RUN apk add --no-cache \
    strongswan \
    iproute2 \
    tcpdump \
    iptables \
    iputils \
    iperf3 \
    curl \
    python3

COPY entrypoint-gateway.sh /entrypoint-gateway.sh
RUN chmod +x /entrypoint-gateway.sh

# Disable bypass-lan - see bypass-lan.conf for why this lab topology needs it off.
COPY bypass-lan.conf /etc/strongswan.d/charon/bypass-lan.conf

ENTRYPOINT ["/entrypoint-gateway.sh"]
