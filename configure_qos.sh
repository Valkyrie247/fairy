#!/usr/bin/env bash
# Configure OVS HTB queues on both ends of the s1--s2 bottleneck.
# Usage inside Mininet CLI: sh ./configure_qos.sh priority
# Baseline: sh ./configure_qos.sh baseline
set -euo pipefail

MODE="${1:-priority}"
PORTS=("s1-eth4" "s2-eth2")

if [[ "$MODE" != "priority" && "$MODE" != "baseline" ]]; then
    echo "Usage: $0 [priority|baseline]"
    exit 1
fi

for port in "${PORTS[@]}"; do
    ovs-vsctl --if-exists clear Port "$port" qos
    if [[ "$MODE" == "baseline" ]]; then
        # Same 5 Mbps bottleneck, but only the default queue.
        ovs-vsctl \
          -- set Port "$port" qos=@qos \
          -- --id=@q0 create Queue other-config:min-rate=5000000 other-config:max-rate=5000000 \
          -- --id=@qos create QoS type=linux-htb other-config:max-rate=5000000 queues:0=@q0
    else
        ovs-vsctl \
          -- set Port "$port" qos=@qos \
          -- --id=@q0 create Queue other-config:min-rate=500000 other-config:max-rate=5000000 \
          -- --id=@q1 create Queue other-config:min-rate=4000000 other-config:max-rate=5000000 \
          -- --id=@qos create QoS type=linux-htb other-config:max-rate=5000000 queues:0=@q0 queues:1=@q1
    fi
done

echo "$MODE mode enabled on ${PORTS[*]} (5 Mbps bottleneck)."
if [[ "$MODE" == "priority" ]]; then
    echo "Queue 1 (DSCP 46 game packets): minimum 4 Mbps."
    echo "Queue 0 (background/default): minimum 0.5 Mbps."
fi
