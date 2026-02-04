import argparse

import plotly.graph_objects as go
import plotly.io as pio


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot epoch vs validation accuracy")
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--html", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    epochs = []
    accs = []

    with open(args.metrics, "r", encoding="utf-8") as f:
        _ = next(f, None)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 3:
                continue
            epochs.append(int(parts[0]))
            accs.append(float(parts[2]))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=epochs,
            y=accs,
            mode="lines+markers",
            line=dict(color="#1f77b4"),
            marker=dict(size=7),
        )
    )
    fig.update_layout(
        title="Validation Accuracy by Epoch",
        xaxis_title="Epoch",
        yaxis_title="Accuracy",
        yaxis=dict(range=[0, 1]),
        template="plotly_white",
        margin=dict(l=60, r=20, t=60, b=50),
    )

    html = pio.to_html(
        fig,
        include_plotlyjs="inline",
        full_html=False,
        config={"displayModeBar": False},
    )
    with open(args.html, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    main()
