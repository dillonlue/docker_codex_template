#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <target_directory>" >&2
  exit 1
fi

target_dir="$1"

if [[ ! -d "$target_dir" ]]; then
  echo "Error: directory not found: $target_dir" >&2
  exit 1
fi

output_dir="$target_dir/output"
raw_dir="$target_dir/raw_data"

if [[ -d "$output_dir" ]]; then
  rm -rf "$output_dir"
fi

if [[ -d "$raw_dir" ]]; then
  rm -rf "$raw_dir"
fi
