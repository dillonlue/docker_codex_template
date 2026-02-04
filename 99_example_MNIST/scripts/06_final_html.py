import argparse
import html
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build final HTML report")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--acc", required=True)
    parser.add_argument("--html", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    all_pngs = []
    for root, _, files in os.walk(args.out_dir):
        for name in files:
            if name.lower().endswith(".png"):
                all_pngs.append(os.path.join(root, name))
    all_pngs.sort()

    test_images_dir = os.path.join(args.out_dir, "05_test_images")
    test_pngs = [p for p in all_pngs if os.path.dirname(p) == test_images_dir]
    other_pngs = [p for p in all_pngs if p not in test_pngs]

    accuracy_lines = []
    if os.path.exists(args.acc):
        with open(args.acc, "r", encoding="utf-8") as f:
            accuracy_lines = [line.strip() for line in f if line.strip()]

    rows = []
    rows.append("<html>")
    rows.append("<head>")
    rows.append("  <meta charset=\"utf-8\" />")
    rows.append("  <title>MNIST Report</title>")
    rows.append("  <style>")
    rows.append("    body { font-family: Arial, sans-serif; margin: 24px; }")
    rows.append("    .grid { display: flex; flex-wrap: wrap; gap: 24px; }")
    rows.append("    .card { border: 1px solid #ddd; padding: 12px; border-radius: 8px; }")
    rows.append("    img { max-width: 420px; height: auto; display: block; }")
    rows.append("    .strip { display: flex; gap: 10px; flex-wrap: nowrap; overflow-x: auto; }")
    rows.append("    .strip img { width: 64px; height: 64px; image-rendering: pixelated; }")
    rows.append("    .section { margin-top: 28px; }")
    rows.append("    .meta { margin-bottom: 16px; }")
    rows.append("  </style>")
    rows.append("</head>")
    rows.append("<body>")
    rows.append("  <h1>MNIST Example Report</h1>")
    rows.append("  <div class=\"meta\">")
    rows.append("    <h3>Test Accuracy</h3>")
    if accuracy_lines:
        rows.append("    <pre>")
        for line in accuracy_lines:
            rows.append(html.escape(line))
        rows.append("    </pre>")
    else:
        rows.append("    <p>No accuracy file found.</p>")
    rows.append("  </div>")
    rows.append("  <div class=\"section\">")
    rows.append("    <h3>Plots</h3>")
    rows.append("    <div class=\"grid\">")
    for png in other_pngs:
        rel_path = os.path.relpath(png, args.out_dir)
        name = os.path.basename(png)
        rows.append("    <div class=\"card\">")
        rows.append(f"      <h4>{html.escape(name)}</h4>")
        rows.append(
            f"      <img src=\"{html.escape(rel_path)}\" alt=\"{html.escape(name)}\" />"
        )
        rows.append("    </div>")
    rows.append("    </div>")
    rows.append("  </div>")
    rows.append("  <div class=\"section\">")
    rows.append("    <h3>Test Images</h3>")
    rows.append("    <div class=\"strip\">")
    for png in test_pngs:
        rel_path = os.path.relpath(png, args.out_dir)
        rows.append(f"      <img src=\"{html.escape(rel_path)}\" alt=\"test\" />")
    rows.append("    </div>")
    rows.append("  </div>")
    rows.append("</body>")
    rows.append("</html>")

    os.makedirs(os.path.dirname(args.html), exist_ok=True)
    with open(args.html, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))


if __name__ == "__main__":
    main()
