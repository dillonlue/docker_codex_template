import argparse
import gzip
import os
import struct
import urllib.request

import numpy as np

URL_BASES = [
    "http://yann.lecun.com/exdb/mnist/",
    "https://storage.googleapis.com/cvdf-datasets/mnist/",
]
FILES = {
    "train_images": "train-images-idx3-ubyte.gz",
    "train_labels": "train-labels-idx1-ubyte.gz",
    "test_images": "t10k-images-idx3-ubyte.gz",
    "test_labels": "t10k-labels-idx1-ubyte.gz",
}


def _download(urls: list[str], dest: str) -> None:
    if os.path.exists(dest):
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    last_err = None
    for url in urls:
        try:
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, dest)
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    raise RuntimeError(f"Failed to download {dest} from known MNIST mirrors") from last_err


def _read_images(path: str) -> np.ndarray:
    with gzip.open(path, "rb") as f:
        magic, count, rows, cols = struct.unpack(">IIII", f.read(16)
        )
        if magic != 2051:
            raise ValueError(f"Unexpected magic number {magic} in {path}")
        data = np.frombuffer(f.read(), dtype=np.uint8)
    return data.reshape(count, rows * cols)


def _read_labels(path: str) -> np.ndarray:
    with gzip.open(path, "rb") as f:
        magic, count = struct.unpack(">II", f.read(8)
        )
        if magic != 2049:
            raise ValueError(f"Unexpected magic number {magic} in {path}")
        data = np.frombuffer(f.read(), dtype=np.uint8)
    return data.reshape(count)


def _write_array(path: str, array: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.save(path, array)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download and prepare MNIST")
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--x-train", required=True)
    parser.add_argument("--y-train", required=True)
    parser.add_argument("--x-val", required=True)
    parser.add_argument("--y-val", required=True)
    parser.add_argument("--x-test", required=True)
    parser.add_argument("--y-test", required=True)
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(args.cache_dir, exist_ok=True)

    paths = {}
    for key, filename in FILES.items():
        dest = os.path.join(args.cache_dir, filename)
        urls = [base + filename for base in URL_BASES]
        _download(urls, dest)
        paths[key] = dest

    X_train_full = _read_images(paths["train_images"]).astype(np.float32) / 255.0
    y_train_full = _read_labels(paths["train_labels"]).astype(np.int64)
    X_test = _read_images(paths["test_images"]).astype(np.float32) / 255.0
    y_test = _read_labels(paths["test_labels"]).astype(np.int64)

    rng = np.random.default_rng(args.seed)
    indices = rng.permutation(X_train_full.shape[0])
    val_size = int(args.val_split * X_train_full.shape[0])
    val_idx = indices[:val_size]
    train_idx = indices[val_size:]

    X_train = X_train_full[train_idx]
    y_train = y_train_full[train_idx]
    X_val = X_train_full[val_idx]
    y_val = y_train_full[val_idx]

    _write_array(args.x_train, X_train)
    _write_array(args.y_train, y_train)
    _write_array(args.x_val, X_val)
    _write_array(args.y_val, y_val)
    _write_array(args.x_test, X_test)
    _write_array(args.y_test, y_test)


if __name__ == "__main__":
    main()
