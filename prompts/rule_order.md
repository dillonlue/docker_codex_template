---
description: Create a Snakemake rule-order DOT file for a pipeline directory
argument-hint: DIR="<target directory or numeric prefix>"
---

Follow this workflow to create `rule_order.dot`:

1) Ensure you are in the repo root. DIR=$DIR
2) If $DIR is missing, ask the user for it and stop.
3) If $DIR is digits only, resolve it to a directory in the repo root matching `{DIR}_*`:
   - If exactly one match exists, set {DIR_TO_USE} to that directory name.
   - If no matches or multiple matches exist, ask the user to clarify the target and stop.
4) If $DIR is not digits only, set {DIR_TO_USE}=$DIR.
5) Verify `{DIR_TO_USE}/Snakefile` exists.
6) Generate the rule graph DOT file at `{DIR_TO_USE}/rule_order.dot`:
   - `snakemake -s {DIR_TO_USE}/Snakefile --rulegraph > {DIR_TO_USE}/rule_order.dot`
7) Confirm the file exists and is non-empty with:
   - `ls -l {DIR_TO_USE}/rule_order.dot`
   - `wc -l {DIR_TO_USE}/rule_order.dot`
8) If `{DIR_TO_USE}/rule_order` (without `.dot`) exists, remove it to keep naming consistent.
9) Report completion and the final file path.
