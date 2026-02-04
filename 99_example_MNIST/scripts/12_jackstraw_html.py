import argparse
import html
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build jackstraw HTML report")
    parser.add_argument("--summary-tsv", required=True)
    parser.add_argument("--pvals-tsv", required=True)
    parser.add_argument("--html", required=True)
    return parser.parse_args()


def read_summary(path: str) -> list[tuple[str, str]]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        header = next(f, None)
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                rows.append((parts[0], parts[1]))
    return rows


def read_pvals(path: str, limit: int = 50) -> list[tuple[str, str, str]]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        header = next(f, None)
        for i, line in enumerate(f):
            if i >= limit:
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3:
                rows.append((parts[0], parts[1], parts[2]))
    return rows


def main() -> None:
    args = parse_args()

    summary_rows = read_summary(args.summary_tsv)
    pvals_rows = read_pvals(args.pvals_tsv)

    rows = []
    rows.append("<html>")
    rows.append("<head>")
    rows.append("  <meta charset=\"utf-8\" />")
    rows.append("  <title>Jackstraw PCA Report</title>")
    rows.append("  <style>")
    rows.append("    body { font-family: Arial, sans-serif; margin: 24px; }")
    rows.append("    table { border-collapse: collapse; margin-top: 12px; }")
    rows.append("    th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; }")
    rows.append("    .section { margin-top: 24px; }")
    rows.append("  </style>")
    rows.append("</head>")
    rows.append("<body>")
    rows.append("  <h1>Jackstraw PCA Summary</h1>")

    rows.append("  <div class=\"section\">")
    rows.append("    <h3>Run Metadata</h3>")
    if summary_rows:
        rows.append("    <table>")
        rows.append("      <tr><th>Key</th><th>Value</th></tr>")
        for key, value in summary_rows:
            rows.append(
                f"      <tr><td>{html.escape(key)}</td><td>{html.escape(value)}</td></tr>"
            )
        rows.append("    </table>")
    else:
        rows.append("    <p>No summary file found.</p>")
    rows.append("  </div>")

    rows.append("  <div class=\"section\">")
    rows.append("    <h3>Sample P-Values (first 50)</h3>")
    if pvals_rows:
        rows.append("    <table>")
        rows.append("      <tr><th>Feature</th><th>PC</th><th>P-Value</th></tr>")
        for feature, pc, pval in pvals_rows:
            rows.append(
                f"      <tr><td>{html.escape(feature)}</td><td>{html.escape(pc)}</td><td>{html.escape(pval)}</td></tr>"
            )
        rows.append("    </table>")
    else:
        rows.append("    <p>No p-values file found.</p>")
    rows.append("  </div>")

    rows.append("</body>")
    rows.append("</html>")

    os.makedirs(os.path.dirname(args.html), exist_ok=True)
    with open(args.html, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))


if __name__ == "__main__":
    main()
