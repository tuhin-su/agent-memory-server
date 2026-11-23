#!/usr/bin/env bash
# Stop the Memory Server Web UI
cd "$(dirname "$0")"

if [ ! -f .pid ]; then
  echo "Not running (no .pid file)."
  exit 0
fi

PID=$(cat .pid)
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  rm -f .pid
  echo "Stopped (PID $PID)."
else
  echo "Process $PID not found. Cleaning up .pid file."
  rm -f .pid
fi
