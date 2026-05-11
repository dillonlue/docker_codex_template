#!/usr/bin/env python3
"""Lightweight static file server for this repo.

Usage:
  python local_server/html_server.py --port 8890

By default, this server only exposes:
  - project_journal/
  - figure_aggregator/
  - analysis directories matching {number}_{name}, with output/ and debugger/ subtrees
"""
from __future__ import annotations

import argparse
import getpass
import hmac
import html
import json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http.cookies import CookieError, SimpleCookie
import io
import os
from pathlib import Path
import re
import secrets
import socket
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse


ALLOWED_ROOT_DIRS = {"project_journal", "figure_aggregator"}
ANALYSIS_DIR_RE = re.compile(r"^\d{2,}_.+")
PDF_VIEWER_PATH = "/__pdf_viewer"
DOT_VIEWER_PATH = "/__dot_viewer"
LOGIN_PATH = "/__login"
ARGO_COMPUTE_NODE_RE = re.compile(r"^argo-\d+$")


def _cookie_name_component(value: str) -> str:
    sanitized = "".join(
        char if (char.isascii() and (char.isalnum() or char == "_")) else "_"
        for char in value.strip()
    ).strip("_")
    return sanitized or "repo"


def _project_cookie_scope(root: Path) -> str:
    env_scope = os.environ.get("LOCAL_SERVER_COOKIE_SCOPE", "").strip()
    if env_scope:
        return env_scope

    project_name_path = root / ".project_directory_name.txt"
    if project_name_path.is_file():
        project_name = project_name_path.read_text(encoding="utf-8").strip()
        if project_name:
            return project_name

    return root.name


def _build_session_cookie_name(root: Path, local_port: str | int) -> str:
    scope = _cookie_name_component(_project_cookie_scope(root))
    port = _cookie_name_component(str(local_port))
    return f"local_server_session_{scope}_{port}"


class FilteredHTTPRequestHandler(SimpleHTTPRequestHandler):
    auth_password = "pritykinlab"
    session_cookie_name = "local_server_session"
    session_token = ""

    def _is_authorized(self) -> bool:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except CookieError:
            return False
        morsel = cookie.get(self.session_cookie_name)
        if morsel is None:
            return False
        return hmac.compare_digest(morsel.value, self.session_token)

    def _redirect_to_login(self) -> None:
        target = f"{LOGIN_PATH}?next={quote(self.path or '/', safe='/?:=&')}"
        self.send_response(303)
        self.send_header("Location", target)
        self.end_headers()

    def _login_next_path(self) -> str:
        next_path = parse_qs(urlparse(self.path).query).get("next", ["/"])[0]
        if not next_path.startswith("/"):
            return "/"
        return next_path

    def _serve_login_page(self, error: str = ""):
        next_path = self._login_next_path()
        error_html = (
            f"<p style='color:#b00020'>{html.escape(error)}</p>" if error else ""
        )
        lines = [
            "<!DOCTYPE html>",
            "<html><head>",
            "<meta charset='utf-8'>",
            "<title>local_server login</title>",
            "</head><body>",
            "<h1>local_server</h1>",
            "<p>Enter the password to continue.</p>",
            error_html,
            f"<form method='post' action='{LOGIN_PATH}'>",
            f"<input type='hidden' name='next' value='{html.escape(next_path, quote=True)}'>",
            "<label>Password <input type='password' name='password' autofocus></label>",
            "<button type='submit'>Open</button>",
            "</form>",
            "</body></html>",
        ]
        encoded = "\n".join(line for line in lines if line).encode("utf-8")
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

    def do_POST(self):
        if urlparse(self.path).path != LOGIN_PATH:
            self.send_error(404, "Not found")
            return
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        form = parse_qs(body)
        password = form.get("password", [""])[0]
        next_path = form.get("next", ["/"])[0]
        if not next_path.startswith("/"):
            next_path = "/"
        if not hmac.compare_digest(password, self.auth_password):
            response = self._serve_login_page("Incorrect password.")
            if response is not None:
                self.copyfile(response, self.wfile)
                response.close()
            return
        self.send_response(303)
        self.send_header(
            "Set-Cookie",
            f"{self.session_cookie_name}={self.session_token}; Path=/; HttpOnly; SameSite=Lax",
        )
        self.send_header("Location", next_path)
        self.end_headers()

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
        if top == DOT_VIEWER_PATH.lstrip("/"):
            return len(parts) == 1
        if top in ALLOWED_ROOT_DIRS:
            return True
        if self._is_analysis_dir(top):
            if len(parts) == 1:
                return True
            if len(parts) == 2 and parts[1].lower().endswith(".html"):
                return True
            if parts[1] in {"output", "debugger"}:
                return True
            # Allow top-level DOT artifacts such as rule_order.dot.
            if len(parts) == 2 and parts[1].lower().endswith(".dot"):
                return True
            return False
        return False

    def send_head(self):
        if urlparse(self.path).path == LOGIN_PATH:
            return self._serve_login_page()

        if not self._is_authorized():
            self._redirect_to_login()
            return None

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == PDF_VIEWER_PATH:
            return self._serve_pdf_viewer()
        if path == DOT_VIEWER_PATH:
            return self._serve_dot_viewer()

        if path.lower().endswith(".html") and "raw" not in query:
            return self._serve_html_with_scroll_restore(path)

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
        if path.lower().endswith(".dot") and "raw" not in query:
            parts = self._parts_from_url_path(path)
            if parts is None or not self._is_allowed_parts(parts):
                self.send_error(404, "Not found")
                return None
            target = f"{DOT_VIEWER_PATH}?{urlencode({'file': path})}"
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

    def _inject_scroll_restore_script(self, key: str) -> str:
        return (
            "<script>\n"
            "(function() {\n"
            "  const key = " + key + ";\n"
            "  function restorePosition() {\n"
            "    try {\n"
            '      const raw = localStorage.getItem(key);\n'
            '      if (!raw) {\n'
            "        return;\n"
            "      }\n"
            "      const y = Number(raw);\n"
            "      if (!Number.isFinite(y)) {\n"
            "        return;\n"
            "      }\n"
            "      const maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);\n"
            "      window.scrollTo(0, Math.min(y, maxY));\n"
            "    } catch (_err) {\n"
            "      return;\n"
            "    }\n"
            "  }\n"
            "\n"
            "  function savePosition() {\n"
            "    try {\n"
            "      const y = window.scrollY || window.pageYOffset || 0;\n"
            "      localStorage.setItem(key, String(y));\n"
            "    } catch (_err) {\n"
            "      return;\n"
            "    }\n"
            "  }\n"
            "\n"
            "  if (document.readyState === \"loading\") {\n"
            '    window.addEventListener("DOMContentLoaded", () => {\n'
            "      requestAnimationFrame(restorePosition);\n"
            '    }, { once: true });\n'
            "  } else {\n"
            "    requestAnimationFrame(restorePosition);\n"
            "  }\n"
            "  window.addEventListener(\"pageshow\", (event) => {\n"
            "    if (event.persisted) {\n"
            "      requestAnimationFrame(restorePosition);\n"
            "    }\n"
            "  });\n"
            "  window.addEventListener(\"scroll\", () => {\n"
            "    if (window.__htmlScrollSaveId) {\n"
            "      return;\n"
            "    }\n"
            "    window.__htmlScrollSaveId = setTimeout(() => {\n"
            "      savePosition();\n"
            "      window.__htmlScrollSaveId = null;\n"
            "    }, 120);\n"
            "  }, { passive: true });\n"
            "  window.addEventListener(\"beforeunload\", savePosition);\n"
            "  window.addEventListener(\"pagehide\", savePosition);\n"
            "})();\n"
            "</script>\n"
        )

    def _serve_html_with_scroll_restore(self, path: str):
        parts = self._parts_from_url_path(path)
        if parts is None or not self._is_allowed_parts(parts):
            self.send_error(404, "Not found")
            return None

        root_path = Path(self.directory).resolve()
        full_path = (root_path / Path(*parts)).resolve()
        if root_path != full_path and root_path not in full_path.parents:
            self.send_error(404, "Not found")
            return None
        if not full_path.exists() or not full_path.is_file():
            self.send_error(404, "Not found")
            return None

        try:
            html_text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            html_text = full_path.read_text(encoding="utf-8", errors="replace")

        inject_at = html_text.lower().rfind("</body>")
        suffix = html_text[inject_at:] if inject_at != -1 else ""
        body_part = html_text[:inject_at] if inject_at != -1 else html_text
        if inject_at == -1:
            inject_at = html_text.lower().rfind("</html>")
            suffix = html_text[inject_at:] if inject_at != -1 else ""
            body_part = html_text[:inject_at] if inject_at != -1 else html_text

        storage_key = json.dumps(path)
        html_text = body_part + self._inject_scroll_restore_script(storage_key) + suffix

        encoded = html_text.encode("utf-8", "surrogateescape")
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f

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
        debugger_dir = root / "debugger"
        entries: list[tuple[str, str]] = []
        for html_file in sorted(root.glob("*.html")):
            if html_file.is_file():
                entries.append((html_file.name, f"/{name}/{html_file.name}"))
        if output_dir.is_dir():
            entries.append(("output/", f"/{name}/output/"))
        if debugger_dir.is_dir():
            entries.append(("debugger/", f"/{name}/debugger/"))
        for dot_file in sorted(root.glob("*.dot")):
            if dot_file.is_file():
                entries.append((dot_file.name, f"/{name}/{dot_file.name}"))
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

    def _resolve_allowed_file(
        self, raw_file: str, allowed_suffixes: tuple[str, ...]
    ) -> tuple[str, Path] | None:
        file_path = unquote(raw_file).strip()
        if not file_path:
            self.send_error(400, "Missing 'file' query parameter")
            return None
        if not file_path.startswith("/"):
            file_path = "/" + file_path
        lower_path = file_path.lower()
        if not any(lower_path.endswith(suffix) for suffix in allowed_suffixes):
            allowed = ", ".join(allowed_suffixes)
            self.send_error(400, f"Only {allowed} files are supported")
            return None

        parts = self._parts_from_url_path(file_path)
        if parts is None or not self._is_allowed_parts(parts):
            self.send_error(404, "Not found")
            return None

        root_path = Path(self.directory).resolve()
        full_path = (root_path / Path(*parts)).resolve()
        if root_path != full_path and root_path not in full_path.parents:
            self.send_error(404, "Not found")
            return None
        if not full_path.exists() or not full_path.is_file():
            self.send_error(404, "Not found")
            return None
        return file_path, full_path

    def _parse_dot_graph(self, text: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        # Supports dot lines like:
        #   0[label = "foo"];
        #   1 -> 2
        node_re = re.compile(
            r'^\s*"?([^"\s\[]+)"?\s*\[\s*label\s*=\s*"([^"]*)"',
            re.IGNORECASE,
        )
        edge_re = re.compile(
            r'^\s*"?([^"\s;]+)"?\s*->\s*"?([^"\s;]+)"?',
            re.IGNORECASE,
        )

        node_labels: dict[str, str] = {}
        edge_set: set[tuple[str, str]] = set()
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            m_node = node_re.match(line)
            if m_node:
                node_id = m_node.group(1)
                label = m_node.group(2).replace("\\n", "\n").replace('\\"', '"')
                node_labels[node_id] = label
                continue
            m_edge = edge_re.match(line)
            if m_edge:
                source = m_edge.group(1)
                target = m_edge.group(2)
                edge_set.add((source, target))

        for source, target in edge_set:
            if source not in node_labels:
                node_labels[source] = source
            if target not in node_labels:
                node_labels[target] = target

        def sort_key(node_id: str) -> tuple[int, int | str]:
            if node_id.isdigit():
                return (0, int(node_id))
            return (1, node_id)

        nodes = [
            {"id": node_id, "label": node_labels[node_id]}
            for node_id in sorted(node_labels.keys(), key=sort_key)
        ]
        edges = [
            {"source": source, "target": target}
            for source, target in sorted(edge_set, key=lambda x: (sort_key(x[0]), sort_key(x[1])))
        ]
        return nodes, edges

    def _extract_rule_and_wildcards(self, label: str) -> tuple[str, dict[str, str]]:
        lines = [line.strip() for line in label.splitlines() if line.strip()]
        if not lines:
            stripped = label.strip()
            return (stripped if stripped else label, {})
        rule_name = lines[0]
        wildcards: dict[str, str] = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                wildcards[key] = value
        return rule_name, wildcards

    def _extract_quoted_strings(self, text: str) -> list[str]:
        values = re.findall(r'f?"([^"]*)"', text)
        values.extend(re.findall(r"f?'([^']*)'", text))
        return values

    def _normalize_io_pattern(self, pattern: str) -> str:
        normalized = pattern.strip()
        normalized = normalized.replace("{{", "{").replace("}}", "}")
        normalized = re.sub(r"\{wc\.([A-Za-z0-9_]+)\}", r"{\1}", normalized)
        normalized = normalized.replace("{OUT_DIR}/", "output/")
        normalized = normalized.replace("{OUT_DIR}", "output")
        normalized = normalized.replace("{BASE_DIR}/", "")
        normalized = normalized.replace("{BASE_DIR}", "")
        normalized = normalized.replace("{SCRIPTS_DIR}/", "scripts/")
        normalized = normalized.replace("{SCRIPTS_DIR}", "scripts")
        normalized = normalized.replace("\\", "/")
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized.startswith("/"):
            normalized = normalized[1:]
        return normalized

    def _substitute_wildcards(self, pattern: str, wildcards: dict[str, str]) -> str:
        resolved = pattern
        for key, value in wildcards.items():
            resolved = resolved.replace("{" + key + "}", value)
        return resolved

    def _canonical_pattern(self, pattern: str) -> str:
        return re.sub(r"\{[^{}]+\}", "{*}", pattern)

    def _pattern_to_regex(self, pattern: str) -> re.Pattern[str]:
        escaped = re.escape(pattern)
        placeholder_replaced = re.sub(r"\\\{[^{}]+\\\}", r"[^/]+", escaped)
        return re.compile(r"^" + placeholder_replaced + r"$")

    def _first_sentence(self, text: str) -> str:
        compact = " ".join(text.split())
        if not compact:
            return ""
        m = re.search(r"[.!?]", compact)
        if m:
            return compact[: m.end()].strip()
        return compact

    def _rule_comment_above(self, lines: list[str], rule_index: int) -> str:
        comment_lines: list[str] = []
        idx = rule_index - 1
        while idx >= 0:
            stripped = lines[idx].strip()
            if not stripped:
                if comment_lines:
                    break
                idx -= 1
                continue
            if stripped.startswith("#") and not stripped.startswith("##"):
                text = stripped[1:].strip()
                if text:
                    comment_lines.append(text)
                idx -= 1
                continue
            break
        if not comment_lines:
            return ""
        comment_lines.reverse()
        return self._first_sentence(" ".join(comment_lines))

    def _build_rule_description(self, rule_name: str, record: dict[str, object]) -> str:
        comment = record.get("comment")
        comment_text = self._first_sentence(comment) if isinstance(comment, str) else ""
        if comment_text:
            return comment_text
        return "No one-sentence Snakefile description found for this rule."

    def _is_generic_io_comment(self, comment: str) -> bool:
        normalized = " ".join(str(comment).lower().split())
        if not normalized:
            return True
        generic_markers = (
            "rows are observations or parameter settings",
            "columns are variables/metrics",
            "columns are computed metrics",
            "x-axis and y-axis are defined by this plotting script",
            "plot shows the named metric",
            "plain-text summary",
            "output text summary",
            "input text summary",
        )
        return any(marker in normalized for marker in generic_markers)

    def _default_io_description(
        self, role: str, line_text: str, resolved_values: list[str]
    ) -> str:
        combined = " ".join([line_text] + resolved_values).lower()
        ext = ""
        for value in resolved_values:
            suffix = Path(value).suffix.lower()
            if suffix:
                ext = suffix
                break
        if not ext:
            m = re.search(r"\.([A-Za-z0-9]+)", line_text)
            if m:
                ext = "." + m.group(1).lower()

        if ext == ".tsv":
            if "01_datasets" in combined:
                return (
                    "Synthetic data table where each row is an observation and each "
                    "column is a feature used by downstream modularity analysis."
                )
            if "eigs" in combined:
                return (
                    "Spectral eigenvalue/eigenvector table produced from adjacency or "
                    "kernel matrix decomposition."
                )
            if "curve" in combined or "resolution" in combined:
                return (
                    "Resolution curve table with one row per resolution setting and "
                    "columns for normalized modularity statistics."
                )
            if "leiden_tsv" in combined or "leiden_labels" in combined:
                return (
                    "Leiden clustering label table keyed by observation with label/"
                    "membership annotations for downstream visualizations."
                )
            if "pca" in combined or "umap" in combined:
                return (
                    "Low-dimensional coordinate table for visualization and "
                    "downstream clustering diagnostics."
                )
            if role == "input":
                return "Input table consumed by this step."
            return (
                "Table artifact used by this analysis step with observations in rows "
                "and variables/features in columns."
            )
        if ext == ".png":
            if "knn_true_labels" in combined or "knn" in combined:
                return (
                    "Scatter-style KNN neighborhood plot showing nearest-neighbor "
                    "relationships and true-label structure."
                )
            if "umap_true_labels" in combined:
                return (
                    "UMAP embedding plot colored by true labels for the downstream "
                    "comparison."
                )
            if "umap_leiden_labels" in combined:
                return (
                    "UMAP embedding plot colored by Leiden labels to compare against true "
                    "partitioning."
                )
            if "barplot" in combined:
                return (
                    "Bar plot summarizing a modularity-related statistic across "
                    "datasets or experiments."
                )
            if "resolution" in combined:
                return (
                    "Resolution sweep curve plot used to assess clustering structure and "
                    "modularity stability."
                )
            if "spectral" in combined:
                return (
                    "Spectral analysis figure summarizing modularity behavior for this "
                    "dataset."
                )
            if "overlay" in combined or "plotly" in combined:
                return "Interactive overlay figure combining multiple dataset-level curves."
            return "Analysis figure generated by the associated processing script."
        if ext == ".txt":
            if role == "input":
                return "Input text summary used as an upstream scalar/summary artifact."
            return "Output text summary with computed scalar statistics or checkpoints."
        if ext == ".html":
            return "HTML report/snippet output for interactive viewing."
        if ext == ".npz":
            return "NumPy archive containing matrix/array outputs for downstream analysis."
        if "umap" in combined:
            return (
                "Directory/path of UMAP artifacts where coordinates and colored cluster "
                "visualizations are generated."
            )
        if "directory(" in line_text:
            return "Directory output containing multiple generated files for this step."
        if role == "input":
            return "Upstream input artifact consumed by this rule."
        return "Downstream output artifact produced by this rule."

    def _build_node_io_items(
        self, items_obj: object, wildcards: dict[str, str], role: str
    ) -> list[dict[str, object]]:
        if not isinstance(items_obj, list):
            return []
        result: list[dict[str, object]] = []
        for raw_item in items_obj:
            if not isinstance(raw_item, dict):
                continue
            raw_lines = raw_item.get("raw_lines")
            line = ""
            if isinstance(raw_lines, list):
                clean_lines = [str(x) for x in raw_lines if str(x).strip()]
                line = "\n".join(clean_lines).strip()
            if not line:
                maybe_line = raw_item.get("line")
                if isinstance(maybe_line, str):
                    line = maybe_line.strip()

            values_obj = raw_item.get("values")
            resolved_values: list[str] = []
            if isinstance(values_obj, list):
                for val in values_obj:
                    if not isinstance(val, str) or not val:
                        continue
                    resolved = self._substitute_wildcards(val, wildcards)
                    if resolved not in resolved_values:
                        resolved_values.append(resolved)

            comment_obj = raw_item.get("comment")
            comment = str(comment_obj).strip() if isinstance(comment_obj, str) else ""
            description = (
                comment
                if comment and not self._is_generic_io_comment(comment)
                else self._default_io_description(role, line, resolved_values)
            )

            result.append(
                {
                    "line": line,
                    "description": description,
                }
            )
        return result

    def _parse_snakefile_rule_io(self, snakefile_path: Path) -> dict[str, dict[str, object]]:
        if not snakefile_path.exists() or not snakefile_path.is_file():
            return {}
        try:
            text = snakefile_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = snakefile_path.read_text(encoding="utf-8", errors="replace")

        lines = text.splitlines()
        rule_re = re.compile(r"^(\s*)rule\s+([A-Za-z0-9_]+)\s*:\s*$")
        ref_re = re.compile(r"rules\.([A-Za-z0-9_]+)\.output(?:\.([A-Za-z0-9_]+))?")
        rules: dict[str, dict[str, object]] = {}

        i = 0
        total = len(lines)
        while i < total:
            m_rule = rule_re.match(lines[i])
            if not m_rule:
                i += 1
                continue

            rule_indent = len(m_rule.group(1))
            rule_name = m_rule.group(2)
            rule_comment = self._rule_comment_above(lines, i)
            record: dict[str, object] = {
                "inputs": [],
                "outputs": [],
                "output_named": {},
                "input_refs": [],
                "comment": rule_comment,
                "input_items": [],
                "output_items": [],
                "input_block": "",
                "output_block": "",
            }
            section_lines: dict[str, list[str]] = {"input": [], "output": []}
            section_comments: dict[str, list[str]] = {"input": [], "output": []}
            active_item: dict[str, dict[str, object] | None] = {"input": None, "output": None}
            i += 1
            section = ""
            while i < total:
                line = lines[i]
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())

                next_rule = rule_re.match(line)
                if next_rule and indent <= rule_indent:
                    break

                if not stripped or stripped.startswith("#"):
                    if section in {"input", "output"} and indent >= rule_indent + 8:
                        dedented = line[rule_indent + 8 :] if len(line) >= rule_indent + 8 else ""
                        section_lines[section].append(dedented.rstrip())
                        if stripped.startswith("#"):
                            comment_text = stripped[1:].strip()
                            if comment_text:
                                section_comments[section].append(comment_text)
                    i += 1
                    continue

                if indent == rule_indent + 4 and stripped in {"input:", "output:"}:
                    section = stripped[:-1]
                    section_comments[section] = []
                    active_item[section] = None
                    i += 1
                    continue

                if indent == rule_indent + 4 and stripped.endswith(":"):
                    section = ""

                if section in {"input", "output"} and indent >= rule_indent + 8:
                    dedented = line[rule_indent + 8 :] if len(line) >= rule_indent + 8 else stripped
                    section_lines[section].append(dedented.rstrip())

                    is_new_item = (
                        indent == rule_indent + 8
                        and bool(stripped)
                        and stripped[0] not in ")]}"
                    )
                    item_list_obj = record.get(f"{section}_items")
                    item_list = item_list_obj if isinstance(item_list_obj, list) else []
                    if is_new_item:
                        pending_comment = " ".join(section_comments[section]).strip()
                        section_comments[section] = []
                        item_entry: dict[str, object] = {
                            "line": stripped.rstrip(","),
                            "raw_lines": [dedented.rstrip()],
                            "comment": pending_comment,
                            "values": [],
                            "refs": [],
                        }
                        item_list.append(item_entry)
                        active_item[section] = item_entry
                    elif active_item.get(section):
                        active_raw_item = active_item[section]
                        if isinstance(active_raw_item, dict):
                            raw_lines_obj = active_raw_item.get("raw_lines")
                            if isinstance(raw_lines_obj, list):
                                raw_lines_obj.append(dedented.rstrip())

                    values = [
                        self._normalize_io_pattern(val)
                        for val in self._extract_quoted_strings(stripped)
                    ]
                    values = [val for val in values if val]
                    active_raw_item = active_item.get(section)
                    if isinstance(active_raw_item, dict):
                        item_values_obj = active_raw_item.get("values")
                        if isinstance(item_values_obj, list):
                            for val in values:
                                if val not in item_values_obj:
                                    item_values_obj.append(val)

                    if section == "input":
                        inputs = record["inputs"]
                        if isinstance(inputs, list):
                            for val in values:
                                if val not in inputs:
                                    inputs.append(val)
                    else:
                        outputs = record["outputs"]
                        if isinstance(outputs, list):
                            for val in values:
                                if val not in outputs:
                                    outputs.append(val)
                        key_match = re.match(
                            r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$",
                            stripped.rstrip(","),
                        )
                        if key_match and values:
                            output_named = record["output_named"]
                            if isinstance(output_named, dict):
                                output_named[key_match.group(1)] = values[0]

                    if section == "input":
                        input_refs = record["input_refs"]
                        if isinstance(input_refs, list):
                            for ref in ref_re.finditer(stripped):
                                ref_pair = (ref.group(1), ref.group(2) or "")
                                input_refs.append(ref_pair)
                                if isinstance(active_raw_item, dict):
                                    refs_obj = active_raw_item.get("refs")
                                    if isinstance(refs_obj, list):
                                        refs_obj.append(ref_pair)
                i += 1

            for sec in ("input", "output"):
                block_lines = section_lines[sec]
                while block_lines and not block_lines[-1].strip():
                    block_lines.pop()
                record[f"{sec}_block"] = "\n".join(block_lines)

            rules[rule_name] = record

        for _ in range(max(1, len(rules))):
            changed = False
            for record in rules.values():
                inputs = record.get("inputs")
                input_refs = record.get("input_refs")
                if not isinstance(inputs, list) or not isinstance(input_refs, list):
                    continue
                for src_rule, output_name in input_refs:
                    src_record = rules.get(str(src_rule))
                    if not src_record:
                        continue
                    candidates: list[str] = []
                    if output_name:
                        output_named = src_record.get("output_named")
                        if isinstance(output_named, dict):
                            val = output_named.get(str(output_name))
                            if isinstance(val, str) and val:
                                candidates.append(val)
                    if not candidates:
                        src_outputs = src_record.get("outputs")
                        if isinstance(src_outputs, list):
                            for val in src_outputs:
                                if isinstance(val, str) and val:
                                    candidates.append(val)
                    for val in candidates:
                        if val not in inputs:
                            inputs.append(val)
                            changed = True
                input_items = record.get("input_items")
                if isinstance(input_items, list):
                    for item in input_items:
                        if not isinstance(item, dict):
                            continue
                        refs_obj = item.get("refs")
                        item_values_obj = item.get("values")
                        if not isinstance(refs_obj, list) or not isinstance(item_values_obj, list):
                            continue
                        for src_rule, output_name in refs_obj:
                            src_record = rules.get(str(src_rule))
                            if not src_record:
                                continue
                            candidates: list[str] = []
                            if output_name:
                                output_named = src_record.get("output_named")
                                if isinstance(output_named, dict):
                                    val = output_named.get(str(output_name))
                                    if isinstance(val, str) and val:
                                        candidates.append(val)
                            if not candidates:
                                src_outputs = src_record.get("outputs")
                                if isinstance(src_outputs, list):
                                    for val in src_outputs:
                                        if isinstance(val, str) and val:
                                            candidates.append(val)
                            for val in candidates:
                                if val not in item_values_obj:
                                    item_values_obj.append(val)
            if not changed:
                break

        return rules

    def _attach_edge_files_from_snakefile(
        self,
        dot_file_path: Path,
        nodes: list[dict[str, str]],
        edges: list[dict[str, object]],
    ) -> None:
        if not nodes or not edges:
            return

        snakefile_path = self._find_related_snakefile(dot_file_path)
        if snakefile_path is None:
            return

        rule_map = self._parse_snakefile_rule_io(snakefile_path)
        if not rule_map:
            return

        node_meta: dict[str, tuple[str, dict[str, str]]] = {}
        for node in nodes:
            node_id = node.get("id", "")
            label = node.get("label", "")
            if not node_id:
                continue
            rule_name, wildcards = self._extract_rule_and_wildcards(label)
            node_meta[node_id] = (rule_name, wildcards)

            rule_record = rule_map.get(rule_name)
            if isinstance(rule_record, dict):
                description = self._build_rule_description(rule_name, rule_record)
                input_block_obj = rule_record.get("input_block")
                output_block_obj = rule_record.get("output_block")
                node["input_block"] = (
                    str(input_block_obj) if isinstance(input_block_obj, str) else ""
                )
                node["output_block"] = (
                    str(output_block_obj) if isinstance(output_block_obj, str) else ""
                )
                node["input_items"] = self._build_node_io_items(
                    rule_record.get("input_items"), wildcards, "input"
                )
                node["output_items"] = self._build_node_io_items(
                    rule_record.get("output_items"), wildcards, "output"
                )
            else:
                description = "No one-sentence Snakefile description found for this rule."
                node["input_block"] = ""
                node["output_block"] = ""
                node["input_items"] = []
                node["output_items"] = []
            description = self._substitute_wildcards(description, wildcards)
            node["description"] = description

        for edge in edges:
            source_id = str(edge.get("source", ""))
            target_id = str(edge.get("target", ""))
            source_meta = node_meta.get(source_id)
            target_meta = node_meta.get(target_id)
            if not source_meta or not target_meta:
                edge["files"] = []
                continue
            source_rule, source_wc = source_meta
            target_rule, target_wc = target_meta

            source_record = rule_map.get(source_rule)
            target_record = rule_map.get(target_rule)
            if not source_record or not target_record:
                edge["files"] = []
                continue

            source_outputs = source_record.get("outputs")
            target_inputs = target_record.get("inputs")
            if not isinstance(source_outputs, list) or not isinstance(target_inputs, list):
                edge["files"] = []
                continue

            resolved_source = []
            for out_path in source_outputs:
                if isinstance(out_path, str) and out_path:
                    resolved = self._substitute_wildcards(out_path, source_wc)
                    if resolved not in resolved_source:
                        resolved_source.append(resolved)
            resolved_target = []
            for in_path in target_inputs:
                if isinstance(in_path, str) and in_path:
                    resolved = self._substitute_wildcards(in_path, target_wc)
                    if resolved not in resolved_target:
                        resolved_target.append(resolved)

            target_set = set(resolved_target)
            target_canon_set = {self._canonical_pattern(path) for path in resolved_target}
            target_regexes = [
                self._pattern_to_regex(path)
                for path in resolved_target
            ]
            matched: list[str] = []
            for src_path in resolved_source:
                src_canon = self._canonical_pattern(src_path)
                src_regex = self._pattern_to_regex(src_path)
                path_matches = src_path in target_set
                if not path_matches and src_canon in target_canon_set:
                    path_matches = True
                if not path_matches:
                    for tgt_path, tgt_regex in zip(resolved_target, target_regexes):
                        if tgt_regex.fullmatch(src_path) or src_regex.fullmatch(tgt_path):
                            path_matches = True
                            break
                if path_matches and src_path not in matched:
                    matched.append(src_path)

            edge["files"] = matched[:60]

    def _find_related_snakefile(self, dot_file_path: Path) -> Path | None:
        resolved = dot_file_path.resolve()
        candidates: list[Path] = []

        # Existing convention for debugger DOT files.
        if resolved.parent.name == "debugger":
            candidates.append(resolved.parent.parent / "Snakefile")

        # New convention for analysis-root DOT files (e.g., rule_order.dot).
        candidates.append(resolved.parent / "Snakefile")

        # Fallback: nearest analysis directory ancestor.
        for parent in resolved.parents:
            if self._is_analysis_dir(parent.name):
                candidates.append(parent / "Snakefile")
                break

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _url_path_for_full_path(self, full_path: Path) -> str:
        root_path = Path(self.directory).resolve()
        rel = full_path.resolve().relative_to(root_path)
        return "/" + "/".join(rel.parts)

    def _select_dot_view_target(self, requested_full_path: Path) -> Path:
        requested_full_path = requested_full_path.resolve()
        if requested_full_path.parent.name == "debugger":
            candidate_rule = requested_full_path.parent / "01_rulegraph.dot"
            if candidate_rule.exists() and candidate_rule.is_file():
                return candidate_rule.resolve()
        return requested_full_path

    def _serve_dot_viewer(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        resolved = self._resolve_allowed_file(query.get("file", [""])[0], (".dot",))
        if resolved is None:
            return None
        file_path, full_path = resolved
        active_path = self._select_dot_view_target(full_path)
        try:
            active_url_path = self._url_path_for_full_path(active_path)
        except Exception:
            active_url_path = file_path

        try:
            dot_text = active_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            dot_text = active_path.read_text(encoding="utf-8", errors="replace")
        nodes, edges = self._parse_dot_graph(dot_text)
        self._attach_edge_files_from_snakefile(active_path, nodes, edges)

        safe_title = html.escape(active_url_path)
        js_nodes = json.dumps(nodes)
        js_edges = json.dumps(edges)

        html_doc = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #0f141a;
      --panel: #151c25;
      --panel-2: #0f131a;
      --border: #2b3644;
      --text: #e8eef6;
      --muted: #9aacbf;
      --accent: #58b6ff;
      --node-bg: #eaf4ff;
      --node-border: #2f6de1;
      --edge: #6f7e90;
    }}
    html, body {{
      margin: 0;
      padding: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      height: 100%;
    }}
    body {{
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }}
    .bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.45rem;
      align-items: center;
      background: var(--panel);
      border-bottom: 1px solid var(--border);
      padding: 0.65rem 0.75rem;
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .bar button {{
      background: var(--panel-2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.35rem 0.55rem;
      cursor: pointer;
    }}
    .bar button:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .spacer {{
      flex: 1;
    }}
    #meta {{
      color: var(--muted);
      font-size: 0.9rem;
      white-space: nowrap;
    }}
    #ruleInfoPanel {{
      position: fixed;
      top: 4.1rem;
      right: 0.8rem;
      width: min(560px, calc(100vw - 1.6rem));
      max-height: min(72vh, calc(100vh - 5rem));
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #121a23;
      color: var(--text);
      padding: 0.55rem 0.75rem;
      overflow: auto;
      z-index: 30;
      box-shadow: 0 14px 36px rgba(0, 0, 0, 0.45);
      display: none;
    }}
    #ruleInfoPanel.open {{
      display: block;
    }}
    #ruleInfoHeader {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }}
    #ruleInfoCloseBtn {{
      margin-left: auto;
      background: #0f131a;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.2rem 0.45rem;
      cursor: pointer;
      font-size: 0.75rem;
    }}
    #ruleInfoCloseBtn:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    #ruleInfoTitle {{
      font-size: 0.82rem;
      color: var(--muted);
      margin-bottom: 0.2rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    #ruleInfoText {{
      font-size: 0.9rem;
      line-height: 1.4;
      color: var(--text);
      min-height: 1.35em;
      white-space: normal;
      word-break: break-word;
    }}
    .rule-info-section {{
      margin-top: 0.55rem;
      border-top: 1px solid #24303d;
      padding-top: 0.5rem;
    }}
    .rule-info-section:first-child {{
      margin-top: 0;
      border-top: none;
      padding-top: 0;
    }}
    .rule-info-section-title {{
      color: var(--muted);
      font-size: 0.8rem;
      margin-bottom: 0.25rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }}
    .rule-info-code {{
      margin: 0.25rem 0 0;
      padding: 0.45rem 0.5rem;
      border: 1px solid #2b3a4b;
      border-radius: 6px;
      background: #0c1219;
      color: #dbe7f5;
      font-size: 0.75rem;
      line-height: 1.3;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }}
    .rule-info-item {{
      margin-top: 0.35rem;
      padding: 0.35rem 0.45rem;
      border-radius: 6px;
      background: #0f1822;
      border: 1px solid #243344;
    }}
    .rule-info-item-line {{
      margin: 0;
      font-size: 0.74rem;
      line-height: 1.28;
      white-space: pre-wrap;
      word-break: break-word;
      color: #d6e4f4;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }}
    .rule-info-item-desc {{
      margin-top: 0.25rem;
      font-size: 0.8rem;
      color: #b8cbe0;
      line-height: 1.35;
    }}
    #viewport {{
      position: relative;
      width: 100%;
      flex: 1;
      min-height: 280px;
      overflow: hidden;
      background:
        radial-gradient(circle at 1px 1px, #17222f 1px, transparent 0) 0 0 / 24px 24px,
        #0c1117;
      user-select: none;
      cursor: grab;
    }}
    #viewport.panning {{
      cursor: grabbing;
    }}
    #scene {{
      position: absolute;
      inset: 0;
      transform-origin: 0 0;
      width: 8000px;
      height: 5000px;
    }}
    #edges {{
      position: absolute;
      inset: 0;
      width: 8000px;
      height: 5000px;
      overflow: visible;
    }}
    .edge {{
      stroke: var(--edge);
      stroke-width: 1.6;
      opacity: 0.85;
      marker-end: url(#arrow);
      pointer-events: none;
      cursor: pointer;
      stroke-linecap: round;
      vector-effect: non-scaling-stroke;
    }}
    .edge.edge-required {{
      stroke: #ff5a5a;
      stroke-width: 2.2;
      opacity: 0.96;
    }}
    .edge.edge-hover {{
      stroke: #94d4ff;
      opacity: 1;
      stroke-width: 2;
    }}
    .edge.edge-required.edge-hover {{
      stroke: #ff3030;
      stroke-width: 2.4;
    }}
    .edge-hit {{
      stroke: transparent;
      opacity: 1;
      stroke-width: 22;
      fill: none;
      pointer-events: stroke;
      cursor: pointer;
      stroke-linecap: round;
      vector-effect: non-scaling-stroke;
    }}
    .edge-label {{
      pointer-events: none;
    }}
    .edge-label-bg {{
      fill: #e8f3ff;
      stroke: #4373b8;
      stroke-width: 1;
      rx: 4;
      ry: 4;
      opacity: 0.95;
    }}
    .edge-label-text {{
      fill: #0d284a;
      font-size: 11px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      white-space: pre;
    }}
    #nodes {{
      position: absolute;
      inset: 0;
      pointer-events: none;
    }}
    .node {{
      position: absolute;
      min-width: 82px;
      max-width: 260px;
      padding: 6px 8px;
      border-radius: 8px;
      border: 1px solid var(--node-border);
      background: var(--node-bg);
      color: #0f1d2f;
      font-size: 12px;
      line-height: 1.2;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
      cursor: move;
      white-space: normal;
      pointer-events: auto;
    }}
    .node.selected {{
      border-color: #1f8fff;
      box-shadow: 0 0 0 2px rgba(31, 143, 255, 0.28), 0 4px 12px rgba(0, 0, 0, 0.22);
    }}
    .node.required {{
      border-color: #d23a3a;
      box-shadow: 0 0 0 2px rgba(210, 58, 58, 0.22), 0 4px 12px rgba(0, 0, 0, 0.2);
      background: #ffe9e9;
    }}
    .node.required .node-title {{
      color: #7d1f1f;
    }}
    .node.required .node-toggle {{
      background: #ffd9d9;
      border-color: #d08484;
      color: #7d1f1f;
    }}
    .node.required .node-wildcards {{
      color: #7d1f1f;
      border-top-color: #d08484;
    }}
    .node.deleted {{
      border-color: #68788c;
      background: #c7d0dc;
      color: #394d63;
      opacity: 0.78;
      filter: grayscale(0.85);
    }}
    .node.dragging {{
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
    }}
    .node-title {{
      font-weight: 600;
      word-break: break-word;
    }}
    .node-toggle {{
      margin-top: 0.35rem;
      font-size: 0.72rem;
      line-height: 1.2;
      background: #d5e7ff;
      color: #12345d;
      border: 1px solid #8baede;
      border-radius: 5px;
      padding: 0.15rem 0.35rem;
      cursor: pointer;
      max-width: 100%;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .node-toggle:hover {{
      border-color: #2f6de1;
      color: #0e2f67;
    }}
    .node-wildcards {{
      margin-top: 0.35rem;
      border-top: 1px dashed #8ca3c5;
      padding-top: 0.3rem;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 0.72rem;
      line-height: 1.25;
      color: #203a5b;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }}
    .node-filter {{
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel-2);
      color: var(--text);
      min-width: 280px;
      max-width: 360px;
    }}
    .node-filter > summary {{
      cursor: pointer;
      padding: 0.35rem 0.55rem;
      user-select: none;
      font-size: 0.9rem;
    }}
    .node-filter-body {{
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
      padding: 0 0.45rem 0.5rem;
    }}
    .node-filter-actions {{
      display: flex;
      gap: 0.35rem;
    }}
    .node-filter-actions button {{
      flex: 1;
    }}
    #nodeSearch {{
      width: 100%;
      box-sizing: border-box;
      background: var(--panel);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.35rem 0.45rem;
    }}
    #nodeFilters {{
      max-height: 230px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #0b1016;
      padding: 0.3rem;
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
    }}
    .node-filter-row {{
      display: flex;
      align-items: flex-start;
      gap: 0.35rem;
      padding: 0.2rem 0.25rem;
      border-radius: 4px;
      font-size: 0.8rem;
      color: #ced8e5;
    }}
    .node-filter-row:hover {{
      background: #17212e;
    }}
    .node-filter-row input {{
      margin-top: 0.1rem;
    }}
    .node-filter-row span {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
  </style>
</head>
<body>
  <div class="bar">
    <button id="autoBtn">Auto Layout</button>
    <details class="node-filter">
      <summary>Node Visibility</summary>
      <div class="node-filter-body">
        <div class="node-filter-actions">
          <button type="button" id="showAllNodesBtn">Show All</button>
          <button type="button" id="hideAllNodesBtn">Hide All</button>
        </div>
        <input id="nodeSearch" type="search" placeholder="Filter nodes">
        <div id="nodeFilters"></div>
      </div>
    </details>
    <div class="spacer"></div>
    <span id="meta"></span>
  </div>
  <div id="ruleInfoPanel">
    <div id="ruleInfoHeader">
      <div id="ruleInfoTitle">Rule Description</div>
      <button id="ruleInfoCloseBtn" type="button">Close</button>
    </div>
    <div id="ruleInfoText">Click a rule node to view its Snakefile comment plus exact input/output blocks and artifact descriptions.</div>
  </div>
  <div id="viewport">
    <div id="scene">
      <svg id="edges" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L6,3 z" fill="#6f7e90"></path>
          </marker>
          <marker id="arrowRequired" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" markerUnits="strokeWidth">
            <path d="M0,0 L0,6 L6,3 z" fill="#ff5a5a"></path>
          </marker>
        </defs>
        <g id="edgeLayer"></g>
        <g id="edgeLabelLayer"></g>
      </svg>
      <div id="nodes"></div>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js"></script>
  <script>
    const nodes = {js_nodes}.map((n) => {{
      const lines = String(n.label || n.id).split("\\n");
      const title = (lines[0] || n.id).trim() || n.id;
      const wildcards = lines.slice(1).map((x) => x.trim()).filter((x) => x.length > 0);
      const wildcardKeys = [];
      for (const line of wildcards) {{
        const idx = line.indexOf(":");
        const key = (idx >= 0 ? line.slice(0, idx) : line).trim();
        if (!key || wildcardKeys.includes(key)) continue;
        wildcardKeys.push(key);
      }}
      const wildcardSummary = wildcardKeys.length > 0 ? wildcardKeys.join(", ") : "";
      return {{
        ...n,
        title,
        wildcards,
        wildcardSummary,
        expanded: false,
        x: 0,
        y: 0,
        w: 0,
        h: 0,
        el: null,
        hidden: false,
        deleted: false,
      }};
    }});
    const edges = {js_edges};

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const viewport = document.getElementById("viewport");
    const scene = document.getElementById("scene");
    const edgeLayer = document.getElementById("edgeLayer");
    const edgeLabelLayer = document.getElementById("edgeLabelLayer");
    const nodesLayer = document.getElementById("nodes");
    const nodeFilters = document.getElementById("nodeFilters");
    const nodeSearch = document.getElementById("nodeSearch");
    const showAllNodesBtn = document.getElementById("showAllNodesBtn");
    const hideAllNodesBtn = document.getElementById("hideAllNodesBtn");
    const ruleInfoPanel = document.getElementById("ruleInfoPanel");
    const ruleInfoCloseBtn = document.getElementById("ruleInfoCloseBtn");
    const ruleInfoTitle = document.getElementById("ruleInfoTitle");
    const ruleInfoText = document.getElementById("ruleInfoText");
    const meta = document.getElementById("meta");

    const view = {{ x: 24, y: 24, scale: 1 }};
    const state = {{
      isPanning: false,
      panStartX: 0,
      panStartY: 0,
      dragNodeId: null,
      dragOffsetX: 0,
      dragOffsetY: 0,
      edgeEls: [],
      filterRows: [],
      selectedNodeId: null,
      requiredNodeIds: new Set(),
      requiredEdgeKeys: new Set(),
    }};

    function clamp(v, min, max) {{
      return Math.max(min, Math.min(max, v));
    }}

    function applyView() {{
      scene.style.transform = `translate(${{view.x}}px, ${{view.y}}px) scale(${{view.scale}})`;
    }}

    function escapeHtml(value) {{
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }}

    function renderRuleItems(items) {{
      if (!Array.isArray(items) || items.length === 0) return "";
      let html = "";
      for (const item of items) {{
        const line = String(item.line || "").trim();
        const desc = String(item.description || "").trim();
        html += '<div class="rule-info-item">';
        if (line) {{
          html += `<pre class="rule-info-item-line">${{escapeHtml(line)}}</pre>`;
        }}
        if (desc) {{
          html += `<div class="rule-info-item-desc">${{escapeHtml(desc)}}</div>`;
        }}
        html += "</div>";
      }}
      return html;
    }}

    function renderRuleSection(title, blockText, items) {{
      const safeTitle = escapeHtml(title);
      const block = String(blockText || "").trim();
      const itemsHtml = renderRuleItems(items);
      if (!block && !itemsHtml) return "";
      let html = `<div class="rule-info-section"><div class="rule-info-section-title">${{safeTitle}}</div>`;
      if (block) {{
        html += `<pre class="rule-info-code">${{escapeHtml(block)}}</pre>`;
      }}
      html += itemsHtml;
      html += "</div>";
      return html;
    }}

    function showRuleInfo(node) {{
      if (!node) return;
      const wildcardSuffix = node.wildcards.length > 0 ? ` (${{node.wildcards.join(", ")}})` : "";
      ruleInfoTitle.textContent = `${{node.title || node.id}}${{wildcardSuffix}}`;
      const description = String(node.description || "").trim();
      const fallbackDescription = "No one-sentence Snakefile description found for this rule.";
      let html = "";
      html += renderRuleSection(
        "Rule Comment",
        "",
        [{{ line: "", description: description || fallbackDescription }}],
      );
      html += renderRuleSection("Input (Snakefile)", node.input_block || "", node.input_items || []);
      html += renderRuleSection("Output (Snakefile)", node.output_block || "", node.output_items || []);
      ruleInfoText.innerHTML = html || escapeHtml(fallbackDescription);
      ruleInfoPanel.classList.add("open");
    }}

    function edgeKey(source, target) {{
      return `${{source}}->${{target}}`;
    }}

    function clearRuleInfo() {{
      ruleInfoTitle.textContent = "Rule Description";
      ruleInfoText.textContent = "Click a rule node to view its Snakefile comment plus exact input/output blocks and artifact descriptions.";
      ruleInfoPanel.classList.remove("open");
    }}

    function updateRequiredHighlightForSelectedNode() {{
      state.requiredNodeIds.clear();
      state.requiredEdgeKeys.clear();
      if (!state.selectedNodeId) return;
      const selected = nodeMap.get(state.selectedNodeId);
      if (!selected || selected.hidden || selected.deleted) return;

      const {{ incoming }} = buildAdjacency();
      const stack = [selected.id];
      state.requiredNodeIds.add(selected.id);
      while (stack.length > 0) {{
        const current = stack.pop();
        for (const source of incoming.get(current) || []) {{
          state.requiredEdgeKeys.add(edgeKey(source, current));
          if (!state.requiredNodeIds.has(source)) {{
            state.requiredNodeIds.add(source);
            stack.push(source);
          }}
        }}
      }}
    }}

    function applyNodeClasses() {{
      for (const n of nodes) {{
        if (!n.el) continue;
        n.el.classList.toggle("deleted", Boolean(n.deleted));
        n.el.classList.toggle("selected", state.selectedNodeId === n.id && !n.hidden);
        n.el.classList.toggle(
          "required",
          state.requiredNodeIds.has(n.id) && !n.hidden && !n.deleted,
        );
      }}
    }}

    function isTypingTarget(target) {{
      if (!target) return false;
      if (target.isContentEditable) return true;
      const tag = target.tagName ? target.tagName.toLowerCase() : "";
      return tag === "input" || tag === "textarea" || tag === "select";
    }}

    function parseSortKey(id) {{
      if (/^\\d+$/.test(id)) {{
        return [0, Number(id)];
      }}
      return [1, id];
    }}

    function nodeComparator(a, b) {{
      const ta = String(a.title || a.label || a.id || "");
      const tb = String(b.title || b.label || b.id || "");
      if (ta < tb) return -1;
      if (ta > tb) return 1;

      const wa = Array.isArray(a.wildcards) ? a.wildcards.join("|") : "";
      const wb = Array.isArray(b.wildcards) ? b.wildcards.join("|") : "";
      if (wa < wb) return -1;
      if (wa > wb) return 1;

      const ka = parseSortKey(a.id);
      const kb = parseSortKey(b.id);
      if (ka[0] !== kb[0]) return ka[0] - kb[0];
      if (ka[1] < kb[1]) return -1;
      if (ka[1] > kb[1]) return 1;
      return 0;
    }}

    function buildAdjacency() {{
      const outgoing = new Map();
      const incoming = new Map();
      const indegree = new Map();
      for (const n of nodes) {{
        outgoing.set(n.id, []);
        incoming.set(n.id, []);
        indegree.set(n.id, 0);
      }}
      for (const e of edges) {{
        if (!outgoing.has(e.source)) outgoing.set(e.source, []);
        if (!incoming.has(e.target)) incoming.set(e.target, []);
        outgoing.get(e.source).push(e.target);
        incoming.get(e.target).push(e.source);
        indegree.set(e.target, (indegree.get(e.target) || 0) + 1);
      }}
      return {{ outgoing, incoming, indegree }};
    }}

    function computeLayersForward() {{
      const {{ outgoing, indegree }} = buildAdjacency();
      const byId = new Map(nodes.map((n) => [n.id, n]));

      const explicitRoots = nodes
        .filter((n) => /^r0*1(?:_|\\b)/i.test(String(n.title || n.label || n.id || "")))
        .sort(nodeComparator)
        .map((n) => n.id);
      const sourceRoots = nodes
        .filter((n) => (indegree.get(n.id) || 0) === 0)
        .sort(nodeComparator)
        .map((n) => n.id);
      const roots = explicitRoots.length > 0 ? explicitRoots : sourceRoots;

      const layer = new Map();
      const queue = [];
      for (const id of roots) {{
        if (layer.has(id)) continue;
        layer.set(id, 0);
        queue.push(id);
      }}

      while (queue.length > 0) {{
        const current = queue.shift();
        const currentLayer = layer.get(current) || 0;
        for (const predecessor of outgoing.get(current) || []) {{
          const candidate = currentLayer + 1;
          const previous = layer.get(predecessor);
          if (!Number.isFinite(previous) || candidate > previous) {{
            layer.set(predecessor, candidate);
            queue.push(predecessor);
          }}
        }}
      }}

      let maxLayer = 0;
      for (const val of layer.values()) {{
        maxLayer = Math.max(maxLayer, val);
      }}
      const remaining = nodes
        .filter((n) => !layer.has(n.id))
        .sort(nodeComparator)
        .map((n) => n.id);
      for (const id of remaining) {{
        maxLayer += 1;
        layer.set(id, maxLayer);
      }}

      for (const [id] of byId) {{
        if (!layer.has(id)) {{
          maxLayer += 1;
          layer.set(id, maxLayer);
        }}
      }}
      return layer;
    }}

    function layoutWithDagre() {{
      if (!window.dagre || !window.dagre.graphlib || !window.dagre.layout) {{
        return false;
      }}
      const g = new window.dagre.graphlib.Graph({{ multigraph: false, compound: false }});
      g.setGraph({{
        rankdir: "LR",
        ranker: "network-simplex",
        nodesep: 42,
        ranksep: 140,
        edgesep: 28,
        marginx: 80,
        marginy: 60,
      }});
      g.setDefaultEdgeLabel(() => ({{}}));
      for (const n of nodes) {{
        g.setNode(n.id, {{
          width: Math.max(90, n.w + 20),
          height: Math.max(32, n.h + 14),
        }});
      }}
      for (const e of edges) {{
        if (!nodeMap.has(e.source) || !nodeMap.has(e.target)) continue;
        g.setEdge(e.source, e.target, {{}});
      }}
      try {{
        window.dagre.layout(g);
      }} catch (_err) {{
        return false;
      }}

      let minX = Infinity;
      let minY = Infinity;
      let placed = 0;
      for (const n of nodes) {{
        const p = g.node(n.id);
        if (!p) continue;
        n.x = p.x - p.width / 2;
        n.y = p.y - p.height / 2;
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        placed += 1;
      }}
      if (placed === 0 || !Number.isFinite(minX) || !Number.isFinite(minY)) {{
        return false;
      }}
      const shiftX = 120 - minX;
      const shiftY = 80 - minY;
      for (const n of nodes) {{
        n.x += shiftX;
        n.y += shiftY;
      }}
      return true;
    }}

    function autoLayoutHeuristic() {{
      const layers = computeLayersForward();
      const {{ outgoing, incoming }} = buildAdjacency();
      const groups = new Map();
      for (const n of nodes) {{
        const l = layers.get(n.id) || 0;
        if (!groups.has(l)) groups.set(l, []);
        groups.get(l).push(n);
      }}
      const sortedLayers = [...groups.keys()].sort((a, b) => a - b);
      for (const l of sortedLayers) {{
        groups.get(l).sort(nodeComparator);
      }}

      const layerOrder = new Map();
      const setLayerOrder = (layerId) => {{
        const map = new Map();
        const group = groups.get(layerId) || [];
        for (let i = 0; i < group.length; i++) {{
          map.set(group[i].id, i);
        }}
        layerOrder.set(layerId, map);
      }};
      for (const l of sortedLayers) {{
        setLayerOrder(l);
      }}

      const sortByNeighborBarycenter = (layerIdx, neighborLayerIdx, useIncomingNeighbors) => {{
        const layerId = sortedLayers[layerIdx];
        const neighborLayerId = sortedLayers[neighborLayerIdx];
        const group = groups.get(layerId) || [];
        const neighborOrder = layerOrder.get(neighborLayerId);
        if (!neighborOrder) return;

        const decorated = group.map((node, idx) => {{
          const neighborIds = useIncomingNeighbors
            ? (incoming.get(node.id) || [])
            : (outgoing.get(node.id) || []);
          let sum = 0;
          let count = 0;
          for (const neighborId of neighborIds) {{
            const pos = neighborOrder.get(neighborId);
            if (!Number.isFinite(pos)) continue;
            sum += pos;
            count += 1;
          }}
          return {{
            node,
            idx,
            hasScore: count > 0,
            score: count > 0 ? sum / count : Number.POSITIVE_INFINITY,
          }};
        }});

        decorated.sort((a, b) => {{
          if (a.hasScore !== b.hasScore) return a.hasScore ? -1 : 1;
          if (a.score !== b.score) return a.score - b.score;
          if (a.idx !== b.idx) return a.idx - b.idx;
          return nodeComparator(a.node, b.node);
        }});
        groups.set(layerId, decorated.map((x) => x.node));
        setLayerOrder(layerId);
      }};

      const sweeps = 8;
      for (let iter = 0; iter < sweeps; iter++) {{
        for (let i = 1; i < sortedLayers.length; i++) {{
          sortByNeighborBarycenter(i, i - 1, true);
        }}
        for (let i = sortedLayers.length - 2; i >= 0; i--) {{
          sortByNeighborBarycenter(i, i + 1, false);
        }}
      }}

      const left = 120;
      const top = 80;
      const layerGap = 170;
      const rowGap = 34;

      const layerWidths = new Map();
      const layerHeights = new Map();
      let maxLayerHeight = 0;
      for (const l of sortedLayers) {{
        const group = groups.get(l) || [];
        let width = 120;
        let height = 0;
        for (const n of group) {{
          width = Math.max(width, n.w + 12);
          height += n.h;
        }}
        if (group.length > 1) {{
          height += rowGap * (group.length - 1);
        }}
        layerWidths.set(l, width);
        layerHeights.set(l, height);
        maxLayerHeight = Math.max(maxLayerHeight, height);
      }}

      const layerX = new Map();
      let cursorX = left;
      for (const l of sortedLayers) {{
        layerX.set(l, cursorX);
        cursorX += (layerWidths.get(l) || 120) + layerGap;
      }}

      for (const l of sortedLayers) {{
        const group = groups.get(l) || [];
        const x = layerX.get(l) || left;
        const layerHeight = layerHeights.get(l) || 0;
        let y = top + (maxLayerHeight - layerHeight) / 2;
        for (const n of group) {{
          n.x = x;
          n.y = y;
          y += n.h + rowGap;
        }}
      }}
    }}

    function autoLayout() {{
      refreshNodeSizes();
      if (!layoutWithDagre()) {{
        autoLayoutHeuristic();
      }}
      applyNodePositions();
      updateEdges();
      updateMeta();
    }}

    function createNodes() {{
      nodesLayer.innerHTML = "";
      for (const n of nodes) {{
        const el = document.createElement("div");
        el.className = "node";
        el.dataset.id = n.id;

        const titleEl = document.createElement("div");
        titleEl.className = "node-title";
        titleEl.textContent = n.title || n.id;
        el.appendChild(titleEl);

        if (n.wildcards.length > 0) {{
          const toggleEl = document.createElement("button");
          toggleEl.type = "button";
          toggleEl.className = "node-toggle";
          el.appendChild(toggleEl);

          const detailsEl = document.createElement("div");
          detailsEl.className = "node-wildcards";
          detailsEl.textContent = n.wildcards.join("\\n");
          detailsEl.hidden = !n.expanded;
          el.appendChild(detailsEl);

          const setToggleText = () => {{
            const icon = n.expanded ? "▼" : "▶";
            const summary = n.wildcardSummary || "wildcards";
            toggleEl.textContent = `${{icon}} ${{summary}}`;
          }};
          setToggleText();

          const onToggle = (evt) => {{
            evt.stopPropagation();
            n.expanded = !n.expanded;
            detailsEl.hidden = !n.expanded;
            setToggleText();
            updateNodeSize(n);
            updateEdges();
          }};
          toggleEl.addEventListener("pointerdown", (evt) => evt.stopPropagation());
          toggleEl.addEventListener("click", onToggle);
        }}

        el.addEventListener("click", (evt) => {{
          evt.stopPropagation();
          if (n.deleted) {{
            n.deleted = false;
          }}
          state.selectedNodeId = n.id;
          showRuleInfo(n);
          applyVisibility();
        }});

        n.el = el;
        nodesLayer.appendChild(el);
      }}
      refreshNodeSizes();
    }}

    function updateNodeSize(n) {{
      if (!n.el) return;
      const rect = n.el.getBoundingClientRect();
      n.w = Math.max(82, rect.width);
      n.h = Math.max(24, rect.height);
    }}

    function refreshNodeSizes() {{
      for (const n of nodes) {{
        updateNodeSize(n);
      }}
    }}

    function shortenLabel(label) {{
      const text = String(label || "").replace(/\\s+/g, " ").trim();
      if (text.length <= 72) return text;
      return text.slice(0, 69) + "...";
    }}

    function updateFilterRows() {{
      for (const row of state.filterRows) {{
        const n = nodeMap.get(row.id);
        if (!n) continue;
        row.checkbox.checked = !n.hidden;
      }}
    }}

    function applyFilterSearch() {{
      const query = nodeSearch.value.trim().toLowerCase();
      for (const row of state.filterRows) {{
        const match = !query || row.searchText.includes(query);
        row.el.style.display = match ? "flex" : "none";
      }}
    }}

    function createNodeFilters() {{
      nodeFilters.innerHTML = "";
      state.filterRows = [];
      const sorted = [...nodes].sort(nodeComparator);
      for (const n of sorted) {{
        const rowEl = document.createElement("label");
        rowEl.className = "node-filter-row";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = !n.hidden;

        const textEl = document.createElement("span");
        const labelText = shortenLabel(n.label || n.id);
        textEl.textContent = `${{n.id}}: ${{labelText}}`;

        rowEl.appendChild(checkbox);
        rowEl.appendChild(textEl);
        nodeFilters.appendChild(rowEl);

        const searchText = `${{n.id}} ${{String(n.label || n.id)}}`.toLowerCase();
        state.filterRows.push({{ id: n.id, el: rowEl, checkbox, searchText }});

        checkbox.addEventListener("change", () => {{
          n.hidden = !checkbox.checked;
          applyVisibility();
        }});
      }}
      applyFilterSearch();
    }}

    function applyNodePositions() {{
      for (const n of nodes) {{
        n.el.style.left = `${{n.x}}px`;
        n.el.style.top = `${{n.y}}px`;
      }}
    }}

    function visibleEdgeCount() {{
      let count = 0;
      for (const e of edges) {{
        const s = nodeMap.get(e.source);
        const t = nodeMap.get(e.target);
        if (!s || !t) continue;
        if (s.hidden || t.hidden || s.deleted || t.deleted) continue;
        count += 1;
      }}
      return count;
    }}

    function updateMeta() {{
      const visibleNodes = nodes.filter((n) => !n.hidden).length;
      const visibleEdges = visibleEdgeCount();
      meta.textContent = `${{visibleNodes}}/${{nodes.length}} nodes, ${{visibleEdges}}/${{edges.length}} edges visible`;
    }}

    function applyVisibility() {{
      for (const n of nodes) {{
        n.el.style.display = n.hidden ? "none" : "block";
      }}
      const selectedNode = state.selectedNodeId ? nodeMap.get(state.selectedNodeId) : null;
      if (!selectedNode || selectedNode.hidden || selectedNode.deleted) {{
        state.selectedNodeId = null;
        clearRuleInfo();
      }}
      updateRequiredHighlightForSelectedNode();
      applyNodeClasses();
      updateFilterRows();
      updateEdges();
      updateMeta();
    }}

    function createEdges() {{
      edgeLayer.innerHTML = "";
      edgeLabelLayer.innerHTML = "";
      state.edgeEls = [];
      for (const e of edges) {{
        const hit = document.createElementNS("http://www.w3.org/2000/svg", "line");
        hit.setAttribute("class", "edge-hit");
        edgeLayer.appendChild(hit);

        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.setAttribute("class", "edge");
        edgeLayer.appendChild(line);

        const labelGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
        labelGroup.setAttribute("class", "edge-label");
        const labelRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        labelRect.setAttribute("class", "edge-label-bg");
        const labelText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        labelText.setAttribute("class", "edge-label-text");
        labelText.setAttribute("x", "0");
        labelText.setAttribute("y", "0");
        labelText.setAttribute("text-anchor", "middle");

        const files = Array.isArray(e.files) ? e.files : [];
        const maxLines = 8;
        const fileLines = files.slice(0, maxLines);
        if (files.length > maxLines) {{
          fileLines.push(`... +${{files.length - maxLines}} more`);
        }}
        if (fileLines.length === 0) {{
          const emptySpan = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
          emptySpan.setAttribute("x", "0");
          emptySpan.setAttribute("dy", "0");
          emptySpan.textContent = "(no output file mapping)";
          labelText.appendChild(emptySpan);
        }} else {{
          for (let idx = 0; idx < fileLines.length; idx++) {{
            const lineText = fileLines[idx];
            const span = document.createElementNS("http://www.w3.org/2000/svg", "tspan");
            span.setAttribute("x", "0");
            span.setAttribute("dy", idx === 0 ? "0" : "14");
            span.textContent = lineText;
            labelText.appendChild(span);
          }}
        }}

        labelGroup.appendChild(labelRect);
        labelGroup.appendChild(labelText);
        edgeLabelLayer.appendChild(labelGroup);
        const bbox = labelText.getBBox();
        labelRect.setAttribute("x", String(bbox.x - 6));
        labelRect.setAttribute("y", String(bbox.y - 4));
        labelRect.setAttribute("width", String(bbox.width + 12));
        labelRect.setAttribute("height", String(bbox.height + 8));
        const labelCenterX = bbox.x + bbox.width / 2;
        const labelCenterY = bbox.y + bbox.height / 2;

        const pair = {{
          edge: e,
          hitEl: hit,
          el: line,
          labelEl: labelGroup,
          labelCenterX,
          labelCenterY,
          showLabel: false,
        }};
        const bindEdgeHandlers = (targetEl) => {{
          targetEl.addEventListener("pointerdown", (evt) => {{
            evt.stopPropagation();
          }});
          targetEl.addEventListener("mouseenter", () => {{
            line.classList.add("edge-hover");
          }});
          targetEl.addEventListener("mouseleave", () => {{
            line.classList.remove("edge-hover");
          }});
          targetEl.addEventListener("click", (evt) => {{
            evt.preventDefault();
            evt.stopPropagation();
            pair.showLabel = !pair.showLabel;
            updateEdges();
          }});
        }};
        bindEdgeHandlers(hit);
        state.edgeEls.push(pair);
      }}
    }}

    function nodeCenter(n) {{
      return {{
        x: n.x + n.w / 2,
        y: n.y + n.h / 2,
      }};
    }}

    function rectBoundaryPointFromCenter(n, dirX, dirY) {{
      const center = nodeCenter(n);
      const halfW = Math.max(1, n.w / 2);
      const halfH = Math.max(1, n.h / 2);
      const absX = Math.abs(dirX);
      const absY = Math.abs(dirY);
      if (absX < 1e-6 && absY < 1e-6) {{
        return center;
      }}
      const scale = 1 / Math.max(absX / halfW, absY / halfH);
      return {{
        x: center.x + dirX * scale,
        y: center.y + dirY * scale,
      }};
    }}

    function directedEdgePoints(sourceNode, targetNode) {{
      const sourceCenter = nodeCenter(sourceNode);
      const targetCenter = nodeCenter(targetNode);
      let dx = targetCenter.x - sourceCenter.x;
      let dy = targetCenter.y - sourceCenter.y;
      if (Math.abs(dx) < 1e-6 && Math.abs(dy) < 1e-6) {{
        dx = 1;
        dy = 0;
      }}
      const length = Math.hypot(dx, dy) || 1;
      const ux = dx / length;
      const uy = dy / length;

      const startOnBorder = rectBoundaryPointFromCenter(sourceNode, dx, dy);
      const endOnBorder = rectBoundaryPointFromCenter(targetNode, -dx, -dy);
      const tailPad = 2;
      const headPad = 8;
      const x1 = startOnBorder.x + ux * tailPad;
      const y1 = startOnBorder.y + uy * tailPad;
      const x2 = endOnBorder.x - ux * headPad;
      const y2 = endOnBorder.y - uy * headPad;
      return {{
        x1,
        y1,
        x2,
        y2,
      }};
    }}

    function updateEdges() {{
      for (const pair of state.edgeEls) {{
        const s = nodeMap.get(pair.edge.source);
        const t = nodeMap.get(pair.edge.target);
        if (!s || !t) continue;
        if (s.hidden || t.hidden || s.deleted || t.deleted) {{
          pair.hitEl.style.display = "none";
          pair.el.style.display = "none";
          pair.labelEl.style.display = "none";
          continue;
        }}
        pair.hitEl.style.display = "block";
        pair.el.style.display = "block";
        const required = state.requiredEdgeKeys.has(edgeKey(pair.edge.source, pair.edge.target));
        pair.el.classList.toggle("edge-required", required);
        pair.el.setAttribute("marker-end", required ? "url(#arrowRequired)" : "url(#arrow)");
        const {{ x1, y1, x2, y2 }} = directedEdgePoints(s, t);
        pair.hitEl.setAttribute("x1", x1.toFixed(2));
        pair.hitEl.setAttribute("y1", y1.toFixed(2));
        pair.hitEl.setAttribute("x2", x2.toFixed(2));
        pair.hitEl.setAttribute("y2", y2.toFixed(2));
        pair.el.setAttribute("x1", x1.toFixed(2));
        pair.el.setAttribute("y1", y1.toFixed(2));
        pair.el.setAttribute("x2", x2.toFixed(2));
        pair.el.setAttribute("y2", y2.toFixed(2));
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        pair.labelEl.setAttribute(
          "transform",
          `translate(${{midX - pair.labelCenterX}}, ${{midY - pair.labelCenterY}})`,
        );
        const show = pair.showLabel;
        pair.labelEl.style.display = show ? "block" : "none";
      }}
    }}

    function graphBounds() {{
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const n of nodes) {{
        if (n.hidden) continue;
        minX = Math.min(minX, n.x);
        minY = Math.min(minY, n.y);
        maxX = Math.max(maxX, n.x + n.w);
        maxY = Math.max(maxY, n.y + n.h);
      }}
      if (!Number.isFinite(minX)) {{
        return {{ minX: 0, minY: 0, maxX: 100, maxY: 100 }};
      }}
      return {{ minX, minY, maxX, maxY }};
    }}

    function fitView() {{
      const pad = 40;
      const b = graphBounds();
      const w = Math.max(1, b.maxX - b.minX);
      const h = Math.max(1, b.maxY - b.minY);
      const vw = viewport.clientWidth;
      const vh = viewport.clientHeight;
      const sx = (vw - 2 * pad) / w;
      const sy = (vh - 2 * pad) / h;
      view.scale = clamp(Math.min(sx, sy), 0.1, 2.5);
      view.x = pad - b.minX * view.scale + (vw - 2 * pad - w * view.scale) / 2;
      view.y = pad - b.minY * view.scale + (vh - 2 * pad - h * view.scale) / 2;
      applyView();
    }}

    function clientToWorld(clientX, clientY) {{
      const rect = viewport.getBoundingClientRect();
      return {{
        x: (clientX - rect.left - view.x) / view.scale,
        y: (clientY - rect.top - view.y) / view.scale,
      }};
    }}

    function onPointerDown(e) {{
      if (e.button !== 0) return;
      const target = e.target;
      const elementTarget =
        target && target.nodeType === 1
          ? target
          : target && target.parentElement
            ? target.parentElement
            : null;
      const nodeEl = elementTarget && elementTarget.closest
        ? elementTarget.closest(".node")
        : null;
      if (nodeEl) {{
        const id = nodeEl.dataset.id;
        const n = nodeMap.get(id);
        if (!n) return;
        const world = clientToWorld(e.clientX, e.clientY);
        state.dragNodeId = id;
        state.dragOffsetX = world.x - n.x;
        state.dragOffsetY = world.y - n.y;
        nodeEl.classList.add("dragging");
        nodeEl.style.zIndex = "5";
        return;
      }}
      state.isPanning = true;
      state.panStartX = e.clientX - view.x;
      state.panStartY = e.clientY - view.y;
      viewport.classList.add("panning");
    }}

    function onPointerMove(e) {{
      if (state.dragNodeId) {{
        const n = nodeMap.get(state.dragNodeId);
        if (!n) return;
        const world = clientToWorld(e.clientX, e.clientY);
        n.x = world.x - state.dragOffsetX;
        n.y = world.y - state.dragOffsetY;
        n.el.style.left = `${{n.x}}px`;
        n.el.style.top = `${{n.y}}px`;
        updateEdges();
        return;
      }}
      if (state.isPanning) {{
        view.x = e.clientX - state.panStartX;
        view.y = e.clientY - state.panStartY;
        applyView();
      }}
    }}

    function onPointerUp() {{
      if (state.dragNodeId) {{
        const n = nodeMap.get(state.dragNodeId);
        if (n && n.el) {{
          n.el.classList.remove("dragging");
          n.el.style.zIndex = "1";
        }}
      }}
      state.dragNodeId = null;
      state.isPanning = false;
      viewport.classList.remove("panning");
    }}

    function onWheel(e) {{
      e.preventDefault();
      const rect = viewport.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const py = e.clientY - rect.top;
      const wx = (px - view.x) / view.scale;
      const wy = (py - view.y) / view.scale;

      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      const nextScale = clamp(view.scale * factor, 0.1, 4.0);
      view.x = px - wx * nextScale;
      view.y = py - wy * nextScale;
      view.scale = nextScale;
      applyView();
    }}

    function deleteSelectedNode() {{
      if (!state.selectedNodeId) return;
      const n = nodeMap.get(state.selectedNodeId);
      if (!n || n.hidden) return;
      n.deleted = true;
      state.selectedNodeId = null;
      clearRuleInfo();
      applyVisibility();
    }}

    document.getElementById("autoBtn").addEventListener("click", () => {{
      autoLayout();
    }});
    showAllNodesBtn.addEventListener("click", () => {{
      for (const n of nodes) {{
        n.hidden = false;
      }}
      applyVisibility();
    }});
    hideAllNodesBtn.addEventListener("click", () => {{
      for (const n of nodes) {{
        n.hidden = true;
      }}
      applyVisibility();
    }});
    ruleInfoCloseBtn.addEventListener("click", () => {{
      state.selectedNodeId = null;
      clearRuleInfo();
      applyVisibility();
    }});
    nodeSearch.addEventListener("input", () => {{
      applyFilterSearch();
    }});

    viewport.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    viewport.addEventListener("wheel", onWheel, {{ passive: false }});
    window.addEventListener("keydown", (event) => {{
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTypingTarget(event.target)) return;
      if (event.key === "Escape" && ruleInfoPanel.classList.contains("open")) {{
        event.preventDefault();
        state.selectedNodeId = null;
        clearRuleInfo();
        applyVisibility();
        return;
      }}
      if (event.key === "Delete") {{
        event.preventDefault();
        deleteSelectedNode();
      }}
    }});

    createNodes();
    createEdges();
    createNodeFilters();
    autoLayout();
    applyVisibility();
    fitView();
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

    def _serve_pdf_viewer(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        resolved = self._resolve_allowed_file(query.get("file", [""])[0], (".pdf",))
        if resolved is None:
            return None
        file_path, full_path = resolved

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
    parser.add_argument("--port", type=int, default=8890, help="Port to bind")
    args = parser.parse_args()

    raw_host = socket.gethostname() or socket.getfqdn() or "<your-server-host>"
    node_host = os.environ.get("SLURMD_NODENAME") or raw_host.split(".", 1)[0]
    slurm_job_id = os.environ.get("SLURM_JOB_ID")
    on_argo_compute_node = bool(ARGO_COMPUTE_NODE_RE.fullmatch(node_host))
    use_cluster_tunnel = bool(slurm_job_id) or on_argo_compute_node
    host = "0.0.0.0" if use_cluster_tunnel else "127.0.0.1"
    display_host = node_host if use_cluster_tunnel else host
    root = Path(".").resolve()
    if not root.exists():
        raise SystemExit(f"Directory does not exist: {root}")
    local_port = args.port

    handler = FilteredHTTPRequestHandler
    handler.directory = str(root)
    handler.session_cookie_name = _build_session_cookie_name(root, local_port)
    handler.session_token = secrets.token_hex(32)

    server = ThreadingHTTPServer((host, args.port), handler)
    print(f"Serving {root} on http://{display_host}:{args.port}")
    print("Password-only login is enabled.")
    print(f"Password: {handler.auth_password}")

    ssh_user = getpass.getuser()

    print("")
    print("From your local computer, run this to forward the port:")
    if use_cluster_tunnel:
        cluster_host = os.environ.get("LOCAL_SERVER_CLUSTER_HOST", "argo.princeton.edu")
        print(
            f"  lsof -ti:{local_port} | xargs kill; "
            f"ssh -N -f -L {local_port}:{node_host}:{args.port} {ssh_user}@{cluster_host}"
        )
        if slurm_job_id:
            print("")
            print("To reconnect to this allocation later, run:")
            print(f"  srun --jobid {slurm_job_id} --overlap --pty bash -l")
    else:
        print(
            f"  lsof -ti:{local_port} | xargs kill; "
            f"ssh -N -L {local_port}:127.0.0.1:{args.port} {ssh_user}@{node_host}"
        )
    print(f"Then open: http://127.0.0.1:{local_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
