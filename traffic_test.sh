#!/usr/bin/env bash
# Run from the Mininet CLI using:
#   h3 iperf3 -s -p 5201 > /tmp/iperf-server.log 2>&1 &
#   h4 bash traffic_test.sh
set -euo pipefail
# Usage: h4 bash traffic_test.sh [duration_seconds] [output_file]
DURATION="${1:-30}"
OUTPUT="${2:-/tmp/fairy-iperf.json}"
iperf3 -c 10.0.0.3 -u -b 8M -t "$DURATION" -p 5201 -J | tee "$OUTPUT"
# Observe game RTT/pending counts in each Pygame client during this run.
# Compare receiver loss/jitter/throughput in the two JSON reports.
