import argparse
import os

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export MNIST training data to TSV")
    parser.add_argument("--x-train", required=True)
    parser.add_argument("--out-tsv", required=True)
    parser.add_argument("--max-samples", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=123)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    X = np.load(args.x_train)

    if args.max_samples > 0 and X.shape[0] > args.max_samples:
        rng = np.random.default_rng(args.seed)
        idx = rng.choice(X.shape[0], size=args.max_samples, replace=False)
        X = X[idx]

    os.makedirs(os.path.dirname(args.out_tsv), exist_ok=True)
    np.savetxt(args.out_tsv, X, delimiter="\t", fmt="%.6f")


if __name__ == "__main__":
    main()
