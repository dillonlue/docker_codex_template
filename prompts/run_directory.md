---
description: Run Snakemake in a target pipeline directory
argument-hint: DIR="<target directory>"
---

Follow this workflow to run a pipeline directory:

1) Ensure you are in the repo root.
2) If $DIR is missing, ask the user to provide the target directory or a numeric prefix (e.g. `99` or `99_example_MNIST`).
3) If $DIR is digits only, resolve it to a directory in the repo root matching `DIR_*`:
   - If exactly one match exists, set {DIR_TO_RUN} to that directory name.
   - If no matches or multiple matches exist, ask the user to clarify the target and stop.
4) Verify the directory exists with `ls -a {DIR_TO_RUN}`.
5) Run `snakemake -c 4 -s {DIR_TO_RUN}/Snakefile`.
6) If it fails, report the error and stop.
