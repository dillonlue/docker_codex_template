import argparse
import os

import numpy as np


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


def cross_entropy(probs: np.ndarray, y: np.ndarray) -> float:
    return -np.mean(np.log(probs[np.arange(len(y)), y] + 1e-9))


def accuracy(logits: np.ndarray, y: np.ndarray) -> float:
    preds = np.argmax(logits, axis=1)
    return float(np.mean(preds == y))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a simple MNIST classifier")
    parser.add_argument("--x-train", required=True)
    parser.add_argument("--y-train", required=True)
    parser.add_argument("--x-val", required=True)
    parser.add_argument("--y-val", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--lr", type=float, default=0.2)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-train", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    X_train = np.load(args.x_train)
    y_train = np.load(args.y_train)
    X_val = np.load(args.x_val)
    y_val = np.load(args.y_val)

    if args.max_train > 0 and X_train.shape[0] > args.max_train:
        rng = np.random.default_rng(args.seed)
        idx = rng.choice(X_train.shape[0], size=args.max_train, replace=False)
        X_train = X_train[idx]
        y_train = y_train[idx]

    n_features = X_train.shape[1]
    num_classes = 10
    rng = np.random.default_rng(args.seed)
    W = rng.normal(scale=0.01, size=(n_features, num_classes)).astype(np.float32)
    b = np.zeros(num_classes, dtype=np.float32)

    os.makedirs(os.path.dirname(args.metrics), exist_ok=True)
    with open(args.metrics, "w", encoding="utf-8") as f:
        f.write("epoch\tval_loss\tval_accuracy\n")

        for epoch in range(1, args.epochs + 1):
            order = rng.permutation(X_train.shape[0])
            X_train = X_train[order]
            y_train = y_train[order]

            for start in range(0, X_train.shape[0], args.batch_size):
                end = start + args.batch_size
                X_batch = X_train[start:end]
                y_batch = y_train[start:end]

                logits = X_batch @ W + b
                probs = softmax(logits)
                loss_grad = probs
                loss_grad[np.arange(len(y_batch)), y_batch] -= 1
                loss_grad /= len(y_batch)

                grad_W = X_batch.T @ loss_grad
                grad_b = loss_grad.sum(axis=0)

                W -= args.lr * grad_W
                b -= args.lr * grad_b

            val_logits = X_val @ W + b
            val_probs = softmax(val_logits)
            val_loss = cross_entropy(val_probs, y_val)
            val_acc = accuracy(val_logits, y_val)
            f.write(f"{epoch}\t{val_loss:.6f}\t{val_acc:.6f}\n")

    os.makedirs(os.path.dirname(args.model), exist_ok=True)
    np.savez(args.model, W=W, b=b)


if __name__ == "__main__":
    main()
