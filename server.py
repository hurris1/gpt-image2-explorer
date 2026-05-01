#!/usr/bin/env python3
"""Simple local HTTP server with CORS headers for the prompt gallery."""

import http.server
import socketserver
import os
import sys
import webbrowser

PORT = 8765
DIR = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

HOST = "0.0.0.0"

def main():
    with socketserver.ThreadingTCPServer((HOST, PORT), Handler) as httpd:
        print(f"\n  GPT Image Prompts Gallery")
        print(f"  Local:   http://localhost:{PORT}")
        print(f"  Network: http://10.10.10.87:{PORT}")
        print(f"  Press Ctrl+C to stop\n")
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Server stopped.")

if __name__ == "__main__":
    main()
