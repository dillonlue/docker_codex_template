# Codex Docker Container
This repo contains the container and related setup for running Codex in full-permission mode.
Codex runs in full-permission "yolo" mode inside the container, meaning it can run any command and edit any file within the container. Docker provides the isolation: even with full permissions, it cannot escape the container or access files outside it.

## Copying this repo
To start a new project, change `.project_directory_name.txt`; set this to the new repo name that you'd like

### Other things this container has access to
1. Latex editor (ask codex to explain code and equations in latex in `project journal`; it should then compile the latex so you can see equations)

## Build Locally
1. git clone the repo
2. set up your Git SSH key so pushes don't require typing a password
3. Download VScode, open the cloned folder
4. Install docker (should be a desktop app)
5. Install codex CLI (using the terminal): https://developers.openai.com/codex/cli/
6. run codex in terminal and sign in
7. Type `codex` in terminal to make sure it is working
8. run `build.sh` which build container like a VM with all your packages; every time packages are added have to rerun this
9. Go into the container by using `shell.sh`; You can run multiple of these to get multiple terminals [I usually have at least one for codex and one for myself]: Should see something like this: `root@078025215da0:/repo#`
10. Inside prompts are a bunch of slash commands. Copy prompts into `~/.codex/prompts/`
11. To see how everything is working run `99_MNIST`; Open htmls using "Live Server" extension in VSCode; Right click on the html that you want to run and click "Open with Live Server"

### Notes:
1. Docker can use lots of memory on computer either by keeping old images or build cache. To see how much memory this is taking up: `docker system df`. To prune all memory run: `docker system prune -af --volumes`; locally this could take 25 GB of memory
2. Read through `AGENTS.md`; gives a sense for how I use docker

## Build On Computer Cluster
Most shared compute clusters (like our argo server) do not allow the Docker daemon for security, so the supported container runtime is Apptainer.
1. Install VScode on cluster: look at this for how to do that: https://github.com/pritykinlab/pritykinlab_onboarding
2. Install codex CLI on the cluster (https://developers.openai.com/codex/cli/); npm via conda then codex via npm; run codex in the conda environment that npm installed in; copy ~/.codex/auth.json from local computer over instead of logging in from the server
3. On cluster git clone the repo
4. Update `apptai/config.sh` with your `APPTAINER_USER`, `APPTAINER_HOST`, and `APPTAINER_REPO_DIR`.
5. Build locally and ship the tarball with `apptainer/01_local_build_tar.sh` then `apptainer/02_local_send.sh`. [right now it's set up to my directory you will have to change this; right now these commands are meant to be run from the root directory outside the container] => goal is to place the tarbell inside apptainer directory on the cluster
6. On cluster, run `srun --mem=64GB -t 24:00:00 --pty bash -l` to get an interactive node with Apptainer access. To keep this open I open `ssh argo` then I use iterm2 to open a tmux session
7. SSH to the server and `cd` into the repo that was cloned
8. On the cluster, build the SIF and start a shell/command with `./apptainer/03_cluster_build.sh`
9. To get into the container run: `./apptainer/04_cluster_run.sh`.
10. On server, tell codex to run everything in `99_MNIST`
12. On server, open html files using the "Live Server" extension

## Things to do
1. Connect VSCode to container
2. Run jupyter notebooks use VSCode inside the container [or run jupyter notebooks within the container a different way]
3. Attach VSCode debugger to the container
