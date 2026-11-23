#!/usr/bin/env python3
"""
Memory Server Web UI
A tiny standalone HTTP server - completely separate from memory-server.
Start: python server.py
Stop:  Ctrl+C  (or kill $(cat .pid))
"""
import os
import sys
import http.server
import socketserver
import signal
import webbrowser
from pathlib import Path

PORT = int(os.environ.get("UI_PORT", 5055))
PID_FILE = Path(__file__).parent / ".pid"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")


def start():
    PID_FILE.write_text(str(os.getpid()))
    print(f"╔══════════════════════════════════════╗")
    print(f"║   Memory Server Web UI               ║")
    print(f"║   http://localhost:{PORT}              ║")
    print(f"║   Press Ctrl+C to stop               ║")
    print(f"╚══════════════════════════════════════╝")

    def _cleanup(sig, frame):
        print("\n  Shutting down...")
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.allow_reuse_address = True
        webbrowser.open(f"http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    start()
