---
description: Refresh the latest on-disk edits for the writing we are already working on.
argument-hint: (no arguments)
---

You are resuming collaboration on a writing file that the user has manually edited.

Goal
- Ensure you are working from the latest on-disk version of the writing we have been editing in this thread.

Process
1. Identify the current writing file from the most recent context in this thread.
2. Re-open that file and use the updated on-disk text as the source of truth.
3. Proceed with the user's next instruction using the refreshed text.

Guardrails
- Do not assume prior in-memory text is current; always reload from disk.
- If the current writing file cannot be confidently identified from context, ask the user for the exact file path.
