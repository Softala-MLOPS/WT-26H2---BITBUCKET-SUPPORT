# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer",
#     "requests",
# ]
# ///
import os
import subprocess
import sys
import time

import typer
from bitbucket_client import BitbucketClient, BitbucketError, slugify

app = typer.Typer()


@app.command()
def main(repo_name: str, org_name: str):
    """Fork the config repository into a working repository (org_name = workspace slug)."""
    client = BitbucketClient.from_config(org_name)
    client.export_git_auth()
    fork_repo(client, repo_name)


def get_working_repo_name(config_repo_name: str):
    if config_repo_name.lower().startswith("config-"):
        default = "-".join(["Working"] + config_repo_name.split("-")[1:])
        return typer.prompt("Enter unique name for your working repository:", type=str, default=default)
    return typer.prompt("Enter unique name for your working repository:", type=str)


def fork_repo(client: BitbucketClient, repo_name: str):
    source_slug = slugify(repo_name)
    if not client.get_repo(source_slug):
        typer.echo(f"Repository '{client.workspace}/{repo_name}' not found.")
        sys.exit(1)

    working_name = get_working_repo_name(repo_name)
    while client.get_repo(slugify(working_name)):
        typer.echo(f"The repository name {working_name} is already present in the workspace! Please provide a different one.")
        working_name = get_working_repo_name(repo_name)
    working_slug = slugify(working_name)

    try:
        typer.echo(f"Forking repository {repo_name} to {working_name}...")
        client.fork_repo(source_slug, working_name)

        # Bitbucket forks asynchronously: wait until the fork exists and has its branches.
        for _ in range(60):
            if client.get_repo(working_slug):
                probe = subprocess.run(
                    ["git", "ls-remote", "--heads", client.clone_url(working_slug)],
                    capture_output=True, text=True,
                )
                if probe.returncode == 0 and "refs/heads/production" in probe.stdout:
                    break
            time.sleep(2)
        else:
            raise BitbucketError("Timed out waiting for the fork to finish.")

        try:
            client.enable_pipelines(working_slug)
        except BitbucketError as e:
            typer.echo(f"Could not enable Pipelines automatically ({e}). Enable it in Repository settings > Pipelines.")

        typer.echo(f"Cloning repository {working_slug}")
        subprocess.run(["git", "clone", client.clone_url(working_slug)], check=True)

        os.chdir(working_slug)
        subprocess.run(["git", "checkout", "-b", "staging", "origin/staging"], check=True)
        subprocess.run(["git", "checkout", "-b", "production", "origin/production"], check=True)
        subprocess.run(["git", "checkout", "development"], check=True)
        os.chdir("../")
    except Exception as e:
        typer.echo(f"Failed to fork repository: {e}")
        sys.exit(1)


if __name__ == "__main__":
    app()
