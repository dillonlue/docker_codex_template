#!/usr/bin/env python3
"""Lightweight static file server for this repo.

Usage:
  python serve_static.py --port 8000 --dir /repo
"""
from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve static files from a directory.")
    parser.add_argument("--dir", default=".", help="Directory to serve")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()

    root = Path(args.dir).resolve()
    if not root.exists():
        raise SystemExit(f"Directory does not exist: {root}")

    handler = SimpleHTTPRequestHandler
    handler.directory = str(root)

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving {root} on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
