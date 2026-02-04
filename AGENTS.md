# Agents Guide

- At the start of a new conversation, check whether a pull is needed. If a pull can be done without a merge conflict, run it before starting work.
- Never install anything directly. If something needs to be installed, say what and ask for permission; only then edit Dockerfile, docker-compose, apt-packages, or requirements files for installations.
- If things aren't running fast enough, increase the timeout to maximum.
- If you edit `project_journal/main.tex`, run `project_journal/compile.sh` before finishing so the PDF stays in sync.
- `papers` directory contains some papers that we might reference

If I ask anything about a particular about a paper please reference `papers` directory; don't ever go on the internet to access a paper

If you see a bunch of files that have been changed but you haven't touched that is ok. Don't warn me about this.

Directory and Script Format
- Every new analysis should start with {number}_{description}; An example of an analysis is `99_example_MNIST` for the example directory structure
- Before starting read `99_example_MNIST/Snakefile`
- Each section of 10 rules is a subanalysis
- The yth subanalysis start with `y0` then the rules for the subanalysis increment the ones digit. There are two subanalysis inside `99_example_MNIST`
- Snakemake is organized so each sub analysis has a header which is "########################..." => look at the example there are three lines to header with an informative name for that subanalysis; in example there is the train and jackstraw subanalyses
- Each rule should be named in sequential some DAG order so `01`, `02`, etc. and the scripts also are ordered reflecting the rule that runs them also the outputs are ordered in same fashion; You can label multiple scripts if running out of rules to reach the subanalysis
- Rules should be sequential and match scripts/outputs (e.g., `r01_*` uses `scripts/01_*` and writes `output/01_*`)
- Inside this directory should be folders: `raw_data`, `scripts`, `debugger`, `output`, `envs`
- `raw_data` should only be populated by explicit download rules (not by `r01_*` by default).
- Most subanalysis can be run without the use of conda. For example, to run only the MNIST subanalysis HTML (e.g., `05_train.html`) use: `snakemake -c 1 -s 99_example_MNIST/Snakefile output/05_train.html`
- When snakemake is using conda enviornemtns, run snakemake using this command `PATH=/usr/local/bin:/opt/conda/bin:$PATH snakemake -c 1 -s 99_example_MNIST/Snakefile --use-conda`
- Only use conda when there are specialized packages such as R and jackstraw in the example; more general purpose packages should be downloaded by docker; tell me you need to download something that might seem general
- Each subanalysis ends with an HTML summary file describing that subanalysis (e.g., `05_train.html`, `12_jackstraw_report.html`).
- Always have `r99_html` which has links to each of the sub analysis and is named `main.html` this is the only output that does not also have numbers at the front
