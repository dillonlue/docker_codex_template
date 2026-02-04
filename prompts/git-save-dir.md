---
description: Create a concise, descriptive commit for changes within a specific directory
argument-hint: DIR="<target directory>"
---

Follow this workflow to save changes in a particular directory:

1) Ensure you are in the repo root.
2) If $DIR is digits only, resolve it to a directory in the repo root matching `DIR_*`:
   - If exactly one match exists, set {DIR_TO_SAVE} to that directory name.
   - If no matches or multiple matches exist, ask the user to clarify the target and stop.
3) Verify the directory exists with `ls -a {DIR_TO_SAVE}`.
4) Inspect changes scoped to {DIR_TO_SAVE}: `git status --porcelain=v1 -- {DIR_TO_SAVE}` and `git diff --stat -- {DIR_TO_SAVE}`.
5) If there are no changes in {DIR_TO_SAVE}, report that and stop.
6) Scan changed files in {DIR_TO_SAVE} for likely ignore candidates:
   - Repeated file patterns (>10 of the same extension or basename pattern).
   - Large files (>100MB).
   - Never add `.gitignore` rules for `.py` files.
   Propose adding ignore rules to `$DIR/.gitignore` (create if needed).
8) Update `{DIR_TO_SAVE}/.gitignore` with the proposed ignore rules (create if needed), then re-check `git status --porcelain=v1 -- {DIR_TO_SAVE}` to confirm the files are ignored.
9) Stage only the directory: `git add -- {DIR_TO_SAVE}`.
10) If the commit would include more than 10 files, ask the user to confirm before committing.
11) Create a concise commit message summarizing the changes in $DIR (Codex chooses the message).
12) Commit: `git commit -m "<message>"`.
13) Push: `git push`.
14) Verify clean tree for {DIR_TO_SAVE}: `git status --porcelain=v1 -- {DIR_TO_SAVE}` (should be empty).
