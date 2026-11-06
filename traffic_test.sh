#!/usr/bin/env bash
# Run from the Mininet CLI using:
#   h3 iperf3 -s -p 5201 > /tmp/iperf-server.log 2>&1 &
#   h4 bash traffic_test.sh
set -euo pipefail
iperf3 -c 10.0.0.3 -u -b 8M -t 30 -p 5201
