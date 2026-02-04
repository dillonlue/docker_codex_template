---
description: Create a debugger shell script for a pipeline step
argument-hint: DIR="<analysis dir>" SCRIPT="<script name>" ARGS="<cli args>"
---

Use this workflow to add a reusable debugger script:

1) Ensure you are in the repo root.
2) If $DIR or $SCRIPT is missing, ask the user to provide them.
3) Verify `$DIR/scripts/$SCRIPT` exists and `$DIR/debugger/` exists (create if needed).
4) Create a debugger script at `$DIR/debugger/<NN>_<name>.sh` (match your rule number).
5) The script must include this pattern so it works anywhere:

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="$BASE_DIR/raw_data"
OUT_DIR="$BASE_DIR/output"
SCRIPTS_DIR="$BASE_DIR/scripts"

# (Optional) Validate required inputs here.

(cd "$BASE_DIR" && python -m pdb "$SCRIPTS_DIR/<script>" <args>)
```

6) Fill in `<script>` and `<args>` using $SCRIPT and $ARGS (from the rule’s CLI).
7) Make the debugger script executable (`chmod +x`).
8) If asked to run it, execute `bash $DIR/debugger/<NN>_<name>.sh`.
