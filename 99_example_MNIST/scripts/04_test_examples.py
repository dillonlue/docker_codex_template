import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Save random MNIST test examples")
    parser.add_argument("--x-test", required=True)
    parser.add_argument("--y-test", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--n-images", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    X_test = np.load(args.x_test)
    y_test = np.load(args.y_test)

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
        label = int(y_test[idx])
        filename = f"04_test_example_{i:02d}_label{label}.png"
        path = os.path.join(args.out_dir, filename)
        plt.imsave(path, image, cmap="gray")


if __name__ == "__main__":
    main()
