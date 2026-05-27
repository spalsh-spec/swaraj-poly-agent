#!/bin/bash
# Serve the Swaraj dashboard locally.
# Reads live.json written by the agent every scan cycle.
# Run from repo root:
#   bash dashboard/serve.sh

echo "Starting Swaraj dashboard at http://localhost:8765"
echo "Open that URL in your browser. Auto-refreshes every 60s."
echo "Press Ctrl+C to stop."
cd "$(dirname "$0")"
python3 -m http.server 8765
