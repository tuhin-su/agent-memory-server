#!/usr/bin/env bash
# Start the Memory Server Web UI
cd "$(dirname "$0")"

if [ -f .pid ] && kill -0 "$(cat .pid)" 2>/dev/null; then
  echo "Already running (PID $(cat .pid)). Open http://localhost:${UI_PORT:-5055}"
  exit 0
fi

echo "Starting Memory UI..."
python3 server.py &
echo $! > .pid
echo "Started at http://localhost:${UI_PORT:-5055}  (PID $(cat .pid))"
