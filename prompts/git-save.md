---
description: Create a concise, descriptive commit for all current changes
argument-hint: MESSAGE="<commit message>"
---

Follow this workflow to save all current git changes:

1) Ensure you are in the repo root; inspect changes with `git status` and `git diff --stat`.
2) If there are no changes, report that and stop.
3) Check sizes of changed files. If any file is >100MB, do not save it. Add it to a local `.gitignore` in its folder.
4) After updating `.gitignore` files, re-check `git status` to confirm the files are ignored.
5) Stage everything else: `git add -A`.
6) If $MESSAGE is provided, use it as the commit message. Otherwise craft a clear message that summarizes what changed and why.
7) Commit: `git commit -m "<message>"`.
8) Push: `git push`.
9) Verify clean tree: `git status` (should report nothing to commit).
