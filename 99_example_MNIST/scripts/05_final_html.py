import argparse
import html
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build final MNIST HTML report")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--acc", required=True)
    parser.add_argument("--plot-html", required=True)
    parser.add_argument("--html", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = args.out_dir

    accuracy_lines = []
    if os.path.exists(args.acc):
        with open(args.acc, "r", encoding="utf-8") as f:
            accuracy_lines = [line.strip() for line in f if line.strip()]

    plot_html = ""
    if os.path.exists(args.plot_html):
        with open(args.plot_html, "r", encoding="utf-8") as f:
            plot_html = f.read()

    test_dir = os.path.join(out_dir, "04_test_images")
    test_pngs = []
    if os.path.isdir(test_dir):
        for name in sorted(os.listdir(test_dir)):
            if name.lower().endswith(".png"):
                test_pngs.append(os.path.join(test_dir, name))

    rows = []
    rows.append("<html>")
    rows.append("<head>")
    rows.append("  <meta charset=\"utf-8\" />")
    rows.append("  <title>MNIST Example Report</title>")
    rows.append("  <style>")
    rows.append("    body { font-family: Arial, sans-serif; margin: 24px; }")
    rows.append("    img { max-width: 420px; height: auto; display: block; }")
    rows.append("    .strip { display: flex; gap: 10px; flex-wrap: nowrap; overflow-x: auto; }")
    rows.append("    .strip img { width: 64px; height: 64px; image-rendering: pixelated; }")
    rows.append("    .meta { margin-bottom: 16px; }")
    rows.append("    .section { margin-top: 28px; }")
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
    rows.append("    <h3>Validation Accuracy</h3>")
    if plot_html:
        rows.append(plot_html)
    else:
        rows.append("    <p>No plot HTML found.</p>")
    rows.append("  </div>")

    rows.append("  <div class=\"section\">")
    rows.append("    <h3>Test Images</h3>")
    rows.append("    <div class=\"strip\">")
    for png in test_pngs:
        rel_path = os.path.relpath(png, out_dir)
        rows.append(
            f"      <img src=\"{html.escape(rel_path)}\" alt=\"test\" />"
        )
    rows.append("    </div>")
    rows.append("  </div>")

    rows.append("</body>")
    rows.append("</html>")

    os.makedirs(os.path.dirname(args.html), exist_ok=True)
    with open(args.html, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))


if __name__ == "__main__":
    main()
