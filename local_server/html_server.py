#!/usr/bin/env python3
"""Lightweight static file server for this repo.

Usage:
  python local_server/html_server.py --port 8000

By default, this server only exposes:
  - project_journal/
  - figure_aggregator/
  - analysis directories matching {number}_{name}, but only their output/ subtree
"""
from __future__ import annotations

import argparse
import getpass
import html
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import io
import os
from pathlib import Path
import re
import socket
from urllib.parse import unquote, urlparse


ALLOWED_ROOT_DIRS = {"project_journal", "figure_aggregator"}
ANALYSIS_DIR_RE = re.compile(r"^\d{2,}_.+")


class FilteredHTTPRequestHandler(SimpleHTTPRequestHandler):
    def _rel_parts(self) -> list[str] | None:
        url_path = urlparse(self.path).path
        rel = unquote(url_path).lstrip("/")
        if not rel:
            return []
        parts = [p for p in Path(rel).parts if p not in {"", "."}]
        if ".." in parts:
            return None
        return parts

    def _is_analysis_dir(self, name: str) -> bool:
        return bool(ANALYSIS_DIR_RE.match(name))

    def _is_allowed(self) -> bool:
        parts = self._rel_parts()
        if parts is None:
            return False
        if len(parts) == 0:
            return True
        top = parts[0]
        if top in ALLOWED_ROOT_DIRS:
            return True
        if self._is_analysis_dir(top):
            if len(parts) == 1:
                return True
            if parts[1] == "output":
                return True
            return False
        return False

    def send_head(self):
        if not self._is_allowed():
            self.send_error(404, "Not found")
            return None
        return super().send_head()

    def list_directory(self, path):
        parts = self._rel_parts()
        if parts is None:
            return self.send_error(404, "Not found")
        if len(parts) == 0:
            return self._list_root()
        top = parts[0]
        if self._is_analysis_dir(top) and len(parts) == 1:
            return self._list_analysis_dir(top)
        return super().list_directory(path)

    def _list_root(self):
        root = Path(self.directory)
        entries: list[tuple[str, str]] = []
        for name in ["project_journal", "figure_aggregator"]:
            p = root / name
            if p.is_dir():
                entries.append((f"{name}/", f"{name}/"))
        analysis = []
        for name in sorted(os.listdir(root)):
            p = root / name
            if not p.is_dir():
                continue
            if self._is_analysis_dir(name):
                analysis.append((f"{name}/", f"{name}/"))
        entries.extend(analysis)
        return self._write_listing("/", entries)

    def _list_analysis_dir(self, name: str):
        root = Path(self.directory) / name
        output_dir = root / "output"
        entries: list[tuple[str, str]] = []
        if output_dir.is_dir():
            entries.append(("output/", f"/{name}/output/"))
        return self._write_listing(f"/{name}/", entries)

    def _write_listing(self, display_path: str, entries: list[tuple[str, str]]):
        title = f"Index of {display_path}"
        lines = [
            "<!DOCTYPE html>",
            "<html><head>",
            "<meta charset='utf-8'>",
            f"<title>{html.escape(title)}</title>",
            "</head><body>",
            f"<h1>{html.escape(title)}</h1>",
            "<ul>",
            "<li><a href='/'>/</a></li>" if display_path != "/" else "",
        ]
        if not entries:
            lines.append("<li>(empty)</li>")
        else:
            for display_name, href in entries:
                lines.append(
                    f"<li><a href='{html.escape(href)}'>"
                    f"{html.escape(display_name)}</a></li>"
                )
        lines.extend(["</ul>", "</body></html>"])
        encoded = "\n".join(line for line in lines if line).encode(
            "utf-8", "surrogateescape"
        )
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve static files from a directory.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    args = parser.parse_args()

    host = "127.0.0.1"
    root = Path(".").resolve()
    if not root.exists():
        raise SystemExit(f"Directory does not exist: {root}")

    handler = FilteredHTTPRequestHandler
    handler.directory = str(root)

    server = ThreadingHTTPServer((host, args.port), handler)
    print(f"Serving {root} on http://{host}:{args.port}")

    local_port = args.port
    ssh_user = getpass.getuser()
    raw_host = socket.gethostname() or socket.getfqdn() or "<your-server-host>"
    ssh_host = raw_host.split(".", 1)[0]
    remote_host = host
    if remote_host in {"0.0.0.0", "::"}:
        remote_host = "127.0.0.1"

    print("")
    print("From your local computer, run this to forward the port:")
    print(
        f"  ssh -N -L {local_port}:{remote_host}:{args.port} "
        f"{ssh_user}@{ssh_host}"
    )
    print(f"Then open: http://127.0.0.1:{local_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
