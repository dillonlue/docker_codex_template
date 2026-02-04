import argparse
import html
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build top-level HTML index")
    parser.add_argument("--mnist-html", required=True)
    parser.add_argument("--jackstraw-html", required=True)
    parser.add_argument("--html", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    rows = []
    rows.append("<html>")
    rows.append("<head>")
    rows.append("  <meta charset=\"utf-8\" />")
    rows.append("  <title>MNIST Reports</title>")
    rows.append("  <style>")
    rows.append("    body { font-family: Arial, sans-serif; margin: 24px; }")
    rows.append("    ul { line-height: 1.8; }")
    rows.append("  </style>")
    rows.append("</head>")
    rows.append("<body>")
    rows.append("  <h1>MNIST Reports</h1>")
    rows.append("  <ul>")
    rows.append(
        "    <li><a href=\"{}\">{}</a></li>".format(
            html.escape(os.path.basename(args.mnist_html)),
            html.escape(os.path.basename(args.mnist_html)),
        )
    )
    rows.append(
        "    <li><a href=\"{}\">{}</a></li>".format(
            html.escape(os.path.basename(args.jackstraw_html)),
            html.escape(os.path.basename(args.jackstraw_html)),
        )
    )
    rows.append("  </ul>")
    rows.append("</body>")
    rows.append("</html>")

    os.makedirs(os.path.dirname(args.html), exist_ok=True)
    with open(args.html, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))


if __name__ == "__main__":
    main()
