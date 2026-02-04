---
description: Run Snakemake in a target pipeline directory
argument-hint: DIR="<target directory>"
---

Follow this workflow to run a pipeline directory:

1) Ensure you are in the repo root. DIR=$DIR
2) If $DIR is digits only, resolve it to a directory in the repo root matching `{DIR}_*`:
   - If exactly one match exists, set {DIR_TO_RUN} to that directory name.
   - If no matches or multiple matches exist, ask the user to clarify the target and stop.
3) Verify the directory exists with `ls -a {DIR_TO_RUN}`.
4) Run `snakemake -c 4 -s {DIR_TO_RUN}/Snakefile`.
5) Keep working on it until it works
