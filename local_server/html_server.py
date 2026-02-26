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
import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import io
import os
from pathlib import Path
import re
import socket
from urllib.parse import parse_qs, unquote, urlencode, urlparse


ALLOWED_ROOT_DIRS = {"project_journal", "figure_aggregator"}
ANALYSIS_DIR_RE = re.compile(r"^\d{2,}_.+")
PDF_VIEWER_PATH = "/__pdf_viewer"


class FilteredHTTPRequestHandler(SimpleHTTPRequestHandler):
    def _rel_parts(self) -> list[str] | None:
        url_path = urlparse(self.path).path
        return self._parts_from_url_path(url_path)

    def _parts_from_url_path(self, url_path: str) -> list[str] | None:
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
        return self._is_allowed_parts(parts)

    def _is_allowed_parts(self, parts: list[str]) -> bool:
        if len(parts) == 0:
            return True
        top = parts[0]
        if top == PDF_VIEWER_PATH.lstrip("/"):
            return len(parts) == 1
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
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == PDF_VIEWER_PATH:
            return self._serve_pdf_viewer()

        if path.lower().endswith(".pdf") and "raw" not in query:
            parts = self._parts_from_url_path(path)
            if parts is None or not self._is_allowed_parts(parts):
                self.send_error(404, "Not found")
                return None
            target = f"{PDF_VIEWER_PATH}?{urlencode({'file': path})}"
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()
            return None

        if not self._is_allowed():
            self.send_error(404, "Not found")
            return None

        # Disable conditional revalidation so regenerated files are never
        # incorrectly served from browser cache via 304 responses.
        for header_name in ("If-Modified-Since", "If-None-Match"):
            if header_name in self.headers:
                del self.headers[header_name]
        return super().send_head()

    def end_headers(self):
        # Disable client/proxy caching for all content served by this helper.
        self.send_header(
            "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"
        )
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

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

    def _serve_pdf_viewer(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        raw_file = query.get("file", [""])[0]
        file_path = unquote(raw_file).strip()
        if not file_path:
            return self.send_error(400, "Missing 'file' query parameter")
        if not file_path.startswith("/"):
            file_path = "/" + file_path
        if not file_path.lower().endswith(".pdf"):
            return self.send_error(400, "Only PDF files are supported")

        parts = self._parts_from_url_path(file_path)
        if parts is None or not self._is_allowed_parts(parts):
            return self.send_error(404, "Not found")

        full_path = (Path(self.directory) / Path(*parts)).resolve()
        if not full_path.exists() or not full_path.is_file():
            return self.send_error(404, "Not found")

        safe_title = html.escape(file_path)
        js_file_path = json.dumps(file_path)
        html_doc = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #111418;
      --panel: #171b22;
      --text: #edf0f5;
      --muted: #9aa4b2;
      --accent: #59b0ff;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    }}
    .bar {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
      background: var(--panel);
      border-bottom: 1px solid #2a3240;
      padding: 0.75rem;
    }}
    .bar input {{
      width: 4.5rem;
      background: #0f1319;
      color: var(--text);
      border: 1px solid #2a3240;
      border-radius: 6px;
      padding: 0.2rem 0.35rem;
    }}
    .bar button {{
      background: #0f1319;
      color: var(--text);
      border: 1px solid #2a3240;
      border-radius: 6px;
      padding: 0.3rem 0.55rem;
      cursor: pointer;
    }}
    .bar button:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .spacer {{
      flex: 1;
    }}
    #status {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    #viewer {{
      padding: 1rem 0;
      display: flex;
      justify-content: center;
    }}
    #pageWrap {{
      position: relative;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.55);
      max-width: calc(100vw - 2rem);
      background: white;
    }}
    #canvas {{
      display: block;
      height: auto;
      max-width: 100%;
    }}
    #textLayer {{
      position: absolute;
      inset: 0;
      overflow: hidden;
      text-align: initial;
      line-height: 1;
      -webkit-text-size-adjust: none;
      text-size-adjust: none;
      transform-origin: 0 0;
      forced-color-adjust: none;
      z-index: 2;
    }}
    #textLayer span,
    #textLayer br {{
      color: transparent;
      position: absolute;
      white-space: pre;
      cursor: text;
      transform-origin: 0 0;
      user-select: text;
    }}
    #textLayer .endOfContent {{
      display: block;
      position: absolute;
      left: 0;
      top: 100%;
      right: 0;
      bottom: 0;
      z-index: -1;
      cursor: default;
      user-select: none;
    }}
    #textLayer.selecting .endOfContent {{
      top: 0;
    }}
    #textLayer span::selection {{
      background: rgba(89, 176, 255, 0.35);
      color: transparent;
    }}
    #textLayer span::-moz-selection {{
      background: rgba(89, 176, 255, 0.35);
      color: transparent;
    }}
    .error {{
      color: #ff8f8f;
      padding: 1rem;
    }}
  </style>
</head>
<body>
  <div class="bar">
    <button id="prev">Prev</button>
    <button id="next">Next</button>
    <label>Page <input id="page" type="number" min="1" step="1"></label>
    <span id="pages">/ ?</span>
    <button id="zoomOut">-</button>
    <label>Zoom <input id="zoom" type="number" min="0.5" max="4" step="0.1"></label>
    <button id="zoomIn">+</button>
    <div class="spacer"></div>
    <span id="status">Loading...</span>
  </div>
  <div id="viewer">
    <div id="pageWrap">
      <canvas id="canvas"></canvas>
      <div id="textLayer" class="textLayer"></div>
    </div>
  </div>
  <div id="error" class="error" hidden></div>

  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <script>
    const filePath = {js_file_path};
    const rawPdfUrl = filePath + (filePath.includes("?") ? "&" : "?") + "raw=1";
    const storageKey = "pdf_state:" + filePath;
    const statusEl = document.getElementById("status");
    const errorEl = document.getElementById("error");
    const pageWrap = document.getElementById("pageWrap");
    const canvas = document.getElementById("canvas");
    const textLayer = document.getElementById("textLayer");
    const ctx = canvas.getContext("2d");
    const pageInput = document.getElementById("page");
    const pagesEl = document.getElementById("pages");
    const zoomInput = document.getElementById("zoom");
    const prevBtn = document.getElementById("prev");
    const nextBtn = document.getElementById("next");
    const zoomInBtn = document.getElementById("zoomIn");
    const zoomOutBtn = document.getElementById("zoomOut");

    const defaultState = {{ page: 1, zoom: 1.25 }};
    let state = defaultState;
    let pdf = null;
    let rendering = false;
    let pendingRender = false;
    let lastVersion = "";

    try {{
      const parsed = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (parsed && Number.isFinite(parsed.page) && Number.isFinite(parsed.zoom)) {{
        state = {{
          page: Math.max(1, Math.floor(parsed.page)),
          zoom: Math.min(4, Math.max(0.5, parsed.zoom))
        }};
      }}
    }} catch (_err) {{
      state = defaultState;
    }}

    pageInput.value = String(state.page);
    zoomInput.value = String(state.zoom.toFixed(2));

    function saveState() {{
      localStorage.setItem(storageKey, JSON.stringify(state));
    }}

    function setStatus(msg) {{
      statusEl.textContent = msg;
    }}

    function showError(msg) {{
      errorEl.hidden = false;
      errorEl.textContent = msg;
      setStatus("Error");
    }}

    async function fetchVersion() {{
      try {{
        const res = await fetch(rawPdfUrl, {{ method: "HEAD", cache: "no-store" }});
        const etag = res.headers.get("ETag") || "";
        const lm = res.headers.get("Last-Modified") || "";
        return etag + "|" + lm;
      }} catch (_err) {{
        return "";
      }}
    }}

    async function renderPage() {{
      if (!pdf) return;
      if (rendering) {{
        pendingRender = true;
        return;
      }}
      rendering = true;
      try {{
        state.page = Math.min(Math.max(1, state.page), pdf.numPages);
        const page = await pdf.getPage(state.page);
        const viewport = page.getViewport({{ scale: state.zoom }});
        const width = Math.ceil(viewport.width);
        const height = Math.ceil(viewport.height);
        const outputScale = window.devicePixelRatio || 1;
        canvas.width = Math.max(1, Math.floor(width * outputScale));
        canvas.height = Math.max(1, Math.floor(height * outputScale));
        canvas.style.width = width + "px";
        canvas.style.height = height + "px";
        pageWrap.style.width = width + "px";
        pageWrap.style.height = height + "px";
        textLayer.style.width = width + "px";
        textLayer.style.height = height + "px";
        await page.render({{
          canvasContext: ctx,
          viewport,
          transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0]
        }}).promise;
        textLayer.innerHTML = "";
        let textContent = null;
        try {{
          textContent = await page.getTextContent({{ disableCombineTextItems: true }});
        }} catch (_err) {{
          textContent = await page.getTextContent();
        }}
        if (typeof window.pdfjsLib.renderTextLayer === "function") {{
          const textLayerTask = window.pdfjsLib.renderTextLayer({{
            textContentSource: textContent,
            textContent,
            container: textLayer,
            viewport,
            textDivs: [],
            enhanceTextSelection: true
          }});
          if (textLayerTask && textLayerTask.promise) {{
            await textLayerTask.promise;
          }}
        }}
        if (!textLayer.querySelector(".endOfContent")) {{
          const end = document.createElement("div");
          end.className = "endOfContent";
          textLayer.appendChild(end);
        }}
        pageInput.value = String(state.page);
        zoomInput.value = String(state.zoom.toFixed(2));
        pagesEl.textContent = "/ " + pdf.numPages;
        setStatus("Loaded " + filePath);
        saveState();
      }} catch (err) {{
        showError("Failed to render PDF page: " + err.message);
      }} finally {{
        rendering = false;
        if (pendingRender) {{
          pendingRender = false;
          renderPage();
        }}
      }}
    }}

    function isTypingTarget(target) {{
      if (!target) return false;
      if (target.isContentEditable) return true;
      const tag = target.tagName ? target.tagName.toLowerCase() : "";
      return tag === "input" || tag === "textarea" || tag === "select";
    }}

    async function changePage(delta, scrollTarget) {{
      if (!pdf) return;
      const nextPage = Math.min(pdf.numPages, Math.max(1, state.page + delta));
      if (nextPage === state.page) return;
      state.page = nextPage;
      await renderPage();
      if (scrollTarget === "top") {{
        window.scrollTo(0, 0);
      }} else if (scrollTarget === "bottom") {{
        window.scrollTo(0, document.documentElement.scrollHeight);
      }}
    }}

    async function loadPdf(forceReload = false) {{
      if (!window.pdfjsLib) {{
        showError("pdf.js failed to load. Check internet access for CDN assets.");
        return;
      }}
      window.pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

      const version = await fetchVersion();
      if (!forceReload && pdf && version && version === lastVersion) {{
        return;
      }}
      const cacheTag = version || String(Date.now());
      const versionedUrl = rawPdfUrl + "&v=" + encodeURIComponent(cacheTag);
      lastVersion = version;

      try {{
        if (pdf) {{
          try {{ await pdf.destroy(); }} catch (_err) {{}}
        }}
        setStatus("Loading PDF...");
        pdf = await window.pdfjsLib.getDocument(versionedUrl).promise;
        state.page = Math.min(Math.max(1, state.page), pdf.numPages);
        await renderPage();
      }} catch (err) {{
        showError("Failed to load PDF: " + err.message);
      }}
    }}

    prevBtn.addEventListener("click", () => {{
      changePage(-1, "bottom");
    }});
    nextBtn.addEventListener("click", () => {{
      changePage(1, "top");
    }});
    pageInput.addEventListener("change", () => {{
      const n = Number(pageInput.value);
      if (!Number.isFinite(n)) return;
      state.page = Math.max(1, Math.floor(n));
      renderPage();
    }});
    zoomInput.addEventListener("change", () => {{
      const z = Number(zoomInput.value);
      if (!Number.isFinite(z)) return;
      state.zoom = Math.min(4, Math.max(0.5, z));
      renderPage();
    }});
    zoomInBtn.addEventListener("click", () => {{
      state.zoom = Math.min(4, +(state.zoom + 0.1).toFixed(2));
      renderPage();
    }});
    zoomOutBtn.addEventListener("click", () => {{
      state.zoom = Math.max(0.5, +(state.zoom - 0.1).toFixed(2));
      renderPage();
    }});

    window.addEventListener("keydown", (event) => {{
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;

      if (event.key === "ArrowLeft") {{
        event.preventDefault();
        changePage(-1, "bottom");
        return;
      }}
      if (event.key === "ArrowRight") {{
        event.preventDefault();
        changePage(1, "top");
      }}
    }});

    setInterval(() => {{
      loadPdf(false);
    }}, 2000);

    window.addEventListener("beforeunload", saveState);
    textLayer.addEventListener("mousedown", () => {{
      textLayer.classList.add("selecting");
    }});
    document.addEventListener("mouseup", () => {{
      textLayer.classList.remove("selecting");
    }});
    loadPdf(true);
  </script>
</body>
</html>
"""

        encoded = html_doc.encode("utf-8")
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
