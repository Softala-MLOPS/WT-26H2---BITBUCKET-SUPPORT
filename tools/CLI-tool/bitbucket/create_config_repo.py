# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyyaml",
#     "typer",
#     "requests",
# ]
# ///
import base64
import glob
import os
import pathlib
import shutil
import subprocess
import sys

import typer
import yaml
from bitbucket_client import BitbucketClient, BitbucketError, slugify

app = typer.Typer()

BRANCHES = ["development", "staging", "production"]
# Template files that belong to other CI platforms and must not end up in a Bitbucket repo.
FOREIGN_CI = [".github", ".gitlab-ci.yml"]


@app.command()
def main(repo_name: str, org_name: str):
    """Create a Bitbucket config repository, branch structure, pipelines and variables.

    org_name is the Bitbucket workspace slug.
    """
    client = BitbucketClient.from_config(org_name)
    client.export_git_auth()

    print(f"Working with repository: {repo_name}")
    print("Creating a new repository...")
    repo = create_repo(client, repo_name)
    slug = repo["slug"]

    print("Pushing the repository to Bitbucket...")
    push_repo()

    print("Creating branches...")
    create_branches()

    print("Adding branch specific files...")
    copy_files()

    print("Setting up the default branch...")
    set_default_branch(client, slug)

    print("Enabling Bitbucket Pipelines...")
    try:
        client.enable_pipelines(slug)
    except BitbucketError as e:
        typer.echo(f"Could not enable Pipelines automatically ({e}). Enable it in Repository settings > Pipelines.")

    print("Setting up the configuration...")
    set_config(client)


def create_repo(client: BitbucketClient, repo_name: str):
    slug = slugify(repo_name)
    repo = client.get_repo(slug)
    if not repo:
        repo = client.create_repo(repo_name, "Upstream repository")
        typer.echo(f"Repository '{repo_name}' created successfully.")
    else:
        typer.echo("Repository already exists.")

    client.check_git_access(repo["slug"])

    if os.path.isdir(repo["slug"]):
        result = subprocess.run(
            ["git", "-C", repo["slug"], "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise BitbucketError(
                f"Local path '{repo['slug']}' exists but is not a Git repository; "
                "move it aside before retrying."
            )
    else:
        subprocess.run(["git", "clone", client.clone_url(repo["slug"])], check=True)
    os.chdir(repo["slug"])
    return repo


def commit_if_staged(message: str, branch: str | None = None) -> None:
    """Commit staged changes only when there are changes, and push the branch."""
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if result.returncode == 1:
        subprocess.run(["git", "commit", "-m", message], check=True)
    elif result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args)
    if branch:
        subprocess.run(["git", "push", "origin", branch], check=True)
    else:
        subprocess.run(["git", "push"], check=True)


def push_repo():
    main_branch = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True, check=True
    ).stdout.strip()
    if not main_branch:  # empty clone may report no branch on older git versions
        main_branch = "main"
        subprocess.run(["git", "checkout", "-b", main_branch], check=True)
    print("Current branch:", main_branch)
    with open("README.md", "w") as f:
        f.write("Readme\n")
    subprocess.run(["git", "add", "."], check=True)
    commit_if_staged("Initial commit", main_branch)


def create_branches():
    results = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True)
    existing = results.stdout.splitlines()
    for branch in BRANCHES:
        if not any(line.strip().endswith(f"remotes/origin/{branch}") for line in existing):
            subprocess.run(["git", "checkout", "-b", branch], check=True)
            subprocess.run(["git", "push", "--set-upstream", "origin", branch], check=True)
            print(f"Branch '{branch}' created successfully.")


def copy_files():
    files_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "files")
    for branch in ["development", "production", "staging"]:
        subprocess.run(["git", "checkout", branch], check=True)
        shutil.copytree(os.path.join(files_dir, branch), ".", dirs_exist_ok=True)
        shutil.copytree(os.path.join(files_dir, "common"), ".", dirs_exist_ok=True)
        # Bitbucket-specific files (bitbucket-pipelines.yml, scripts/)
        shutil.copytree(os.path.join(files_dir, "bitbucket", branch), ".", dirs_exist_ok=True)

        for leftover in FOREIGN_CI:
            if os.path.isdir(leftover):
                shutil.rmtree(leftover)
            elif os.path.exists(leftover):
                os.remove(leftover)

        subprocess.run(["git", "add", "."], check=True)
        commit_if_staged(f"Add {branch} files")


def set_default_branch(client: BitbucketClient, slug: str):
    try:
        client.set_default_branch(slug, "development")
        typer.echo("Default branch set to 'development'.")
    except BitbucketError as e:
        typer.echo(
            f"Could not set the default branch automatically ({e}).\n"
            "Set it manually: Repository settings > Repository details > Main branch = development."
        )


def _ask_int(prompt, valid):
    while True:
        try:
            value = int(input(prompt))
            if value in valid:
                return value
        except ValueError:
            pass
        print(f"Invalid input. Please choose one of {sorted(valid)}.")


def _load_existing_config():
    choice = _ask_int("Choose an option (1: Give a config file PATH, 2: Give a config file NAME): ", {1, 2})
    if choice == 1:
        path = input("input the PATH of config .yaml file that you want to use: ")
        if not os.path.exists(path):
            print(f"{path} doesn't exist")
            sys.exit(1)
        yaml_files = [path]
    else:
        name = input("input the NAME of config .yaml file that you want to use: ")
        name = name[:-5] if name.endswith(".yaml") else name
        yaml_files = glob.glob(f"{os.path.expanduser('~')}/**/{name}.yaml", recursive=True, include_hidden=True)
        if not yaml_files:
            print(f"{name} doesn't exist")
            sys.exit(1)
    if len(yaml_files) > 1:
        for i, p in enumerate(yaml_files, 1):
            print(f"[{i}] {p}")
        idx = _ask_int("Multiple configs found, choose which one to use: ", set(range(1, len(yaml_files) + 1)))
        yaml_files = [yaml_files[idx - 1]]
    with open(yaml_files[0]) as f:
        return yaml.safe_load(f)


def set_config(client: BitbucketClient):
    """Store Kubeflow/SSH settings as workspace-level Pipelines variables."""
    choice = _ask_int(
        "Choose an option (1: Interactively create config, 2: Copy an existing config.yaml, 3: Default everything (DEBUG)): ",
        {1, 2, 3},
    )
    defaults = {
        "KUBEFLOW_ENDPOINT": "http://localhost:8080",
        "KUBEFLOW_USERNAME": "user@example.com",
        "KUBEFLOW_PASSWORD": "12341234",
        "REMOTE_CLUSTER_SSH_PRIVATE_KEY_PATH": "",
        "REMOTE_CLUSTER_SSH_IP": "",
        "REMOTE_CLUSTER_SSH_USERNAME": "",
    }
    if choice == 1:
        config = {
            "KUBEFLOW_ENDPOINT": input("Specify Kubeflow endpoint (default: http://localhost:8080): ").strip() or defaults["KUBEFLOW_ENDPOINT"],
            "KUBEFLOW_USERNAME": input("Specify Kubeflow username (default: user@example.com): ").strip() or defaults["KUBEFLOW_USERNAME"],
            "KUBEFLOW_PASSWORD": input("Specify Kubeflow password (default: 12341234): ").strip() or defaults["KUBEFLOW_PASSWORD"],
            "REMOTE_CLUSTER_SSH_PRIVATE_KEY_PATH": input("Add remote cluster private key file path (default: empty): ").strip(),
            "REMOTE_CLUSTER_SSH_IP": input("Specify remote cluster IP: ").strip(),
            "REMOTE_CLUSTER_SSH_USERNAME": input("Add remote cluster username: ").strip(),
        }
        with open("config.yaml", "w") as f:
            yaml.dump(config, f, sort_keys=False)
        print("Configuration saved to 'config.yaml'.")
    elif choice == 2:
        config = _load_existing_config()
    else:
        config = defaults

    if not config or "KUBEFLOW_ENDPOINT" not in config:
        sys.exit("Error: The config seems to be malformed!")

    secured_keys = {"KUBEFLOW_PASSWORD"}
    for key, value in config.items():
        if key == "REMOTE_CLUSTER_SSH_PRIVATE_KEY_PATH":
            if value and os.path.isfile(pathlib.Path(value)):
                with open(value, "rb") as f:
                    # Bitbucket variables are single-line, so the key is stored base64 encoded;
                    # scripts/setup_ssh_tunnel.sh decodes it.
                    encoded = base64.b64encode(f.read()).decode()
                client.set_variable("REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64", encoded, secured=True)
            else:
                print(f'SSH key path "{value}" does not point to a valid SSH key! Skipping...')
        elif value:
            client.set_variable(key, str(value), secured=key in secured_keys)
        else:
            print(f'"{key}" is empty! Skipping...')


if __name__ == "__main__":
    app()
