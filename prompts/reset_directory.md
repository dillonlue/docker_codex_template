---
description: Remove output/ and raw_data/ under a target pipeline directory
argument-hint: DIR="<target directory>"
---

Follow this workflow to reset a pipeline directory:

1) Ensure you are in the repo root. DIR=$DIR
2) If $DIR is digits only, resolve it to a directory in the repo root matching `{DIR}_*`:
   - If exactly one match exists, set {DIR_TO_DEL} to that directory name.
   - If no matches or multiple matches exist, ask the user to clarify the target and stop.
3) Verify the directory exists with `ls -a {DIR_TO_DEL}`.
4) Run `./reset_directory.sh {DIR_TO_DEL}`.
5) Confirm `output/` and `raw_data/` are removed by checking `ls -a {DIR_TO_DEL}`.
