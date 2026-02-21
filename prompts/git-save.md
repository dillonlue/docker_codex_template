---
description: Create a concise, descriptive commit for all current changes
argument-hint: MESSAGE="<commit message>"
---

Follow this workflow to save all current git changes:

1) Ensure you are in the repo root; inspect changes with `git status` and `git diff --stat`.
2) If there are no changes, report that and stop.
3) Scan `git status` for repeated file patterns (by extension or basename pattern). If any pattern appears >10 times (e.g., many `.png`), do not save those files. Add ignore rules to a local `.gitignore` in the folder where the files live (not the repo root unless they are in root).
   - Never add `.gitignore` rules for `.py` files or `.sh` files.
4) Check sizes of changed files. If any file is >100MB, do not save it. Add it to a local `.gitignore` in its folder.
5) After updating `.gitignore` files, re-check `git status` to confirm the files are ignored.
6) Stage everything else: `git add -A`.
7) If $MESSAGE is provided, use it as the commit message. Otherwise craft a clear message that summarizes what changed and why.
8) Commit: `git commit -m "<message>"`.
9) Push: `git push`.
10) Verify clean tree: `git status` (should report nothing to commit).
