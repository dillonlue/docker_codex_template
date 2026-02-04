import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show test images with predictions")
    parser.add_argument("--model", required=True)
    parser.add_argument("--x-test", required=True)
    parser.add_argument("--y-test", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--acc", required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--n-images", type=int, default=25)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = np.load(args.model)
    W = model["W"]
    b = model["b"]

    X_test = np.load(args.x_test)
    y_test = np.load(args.y_test)

    logits = X_test @ W + b
    preds = np.argmax(logits, axis=1)
    acc = float(np.mean(preds == y_test))

    os.makedirs(args.out_dir, exist_ok=True)
    for name in os.listdir(args.out_dir):
        if name.lower().endswith(".png"):
            try:
                os.remove(os.path.join(args.out_dir, name))
            except OSError:
                pass

    rng = np.random.default_rng(args.seed)
    indices = rng.choice(X_test.shape[0], size=args.n_images, replace=False)

    for i, idx in enumerate(indices, start=1):
        image = X_test[idx].reshape(28, 28)
        fig, ax = plt.subplots(figsize=(2, 2))
        ax.imshow(image, cmap="gray")
        ax.set_title(f"p:{preds[idx]} t:{y_test[idx]}", fontsize=8)
        ax.axis("off")
        path = os.path.join(args.out_dir, f"{i:02d}.png")
        fig.tight_layout(pad=0.2)
        fig.savefig(path, dpi=150)
        plt.close(fig)

    os.makedirs(os.path.dirname(args.acc), exist_ok=True)
    with open(args.acc, "w", encoding="utf-8") as f:
        f.write(f"test_accuracy\t{acc:.6f}\n")
        f.write(f"num_samples\t{X_test.shape[0]}\n")


if __name__ == "__main__":
    main()
