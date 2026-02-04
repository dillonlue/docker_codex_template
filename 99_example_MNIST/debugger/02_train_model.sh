#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="$BASE_DIR/raw_data"
OUT_DIR="$BASE_DIR/output"
SCRIPTS_DIR="$BASE_DIR/scripts"

X_TRAIN="$RAW_DIR/01_X_train.npy"
Y_TRAIN="$RAW_DIR/01_y_train.npy"
X_VAL="$RAW_DIR/01_X_val.npy"
Y_VAL="$RAW_DIR/01_y_val.npy"

MODEL_OUT="$OUT_DIR/02_model.npz"
METRICS_OUT="$OUT_DIR/02_val_metrics.tsv"

if [[ ! -f "$X_TRAIN" || ! -f "$Y_TRAIN" || ! -f "$X_VAL" || ! -f "$Y_VAL" ]]; then
  echo "Missing MNIST data. Run the download step first (Snakemake rule r01_download)." >&2
  exit 1
fi

(cd "$BASE_DIR" && python -m pdb "$SCRIPTS_DIR/02_train_model.py" \
  --x-train "$X_TRAIN" --y-train "$Y_TRAIN" \
  --x-val "$X_VAL" --y-val "$Y_VAL" \
  --model "$MODEL_OUT" --metrics "$METRICS_OUT" \
  --epochs "${EPOCHS:-5}" --lr "${LR:-0.2}" \
  --batch-size "${BATCH_SIZE:-128}" --max-train "${MAX_TRAIN:-20000}" \
  --seed "${SEED:-42}")
