# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer",
#     "requests",
# ]
# ///
import sys

import typer

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "bitbucket"))
from bitbucket_client import CONFIG_FILE, BitbucketClient, BitbucketError, save_config  # noqa: E402

app = typer.Typer()


@app.command()
def main():
    """Configure Bitbucket Cloud authentication (REST API, no CLI needed)."""
    typer.echo("Configuring Bitbucket Cloud authentication...")
    typer.echo(
        "Use an Atlassian *API token* (account email + token) or a *workspace access token*.\n"
        "Needed scopes: repository read/write/admin, pipeline read/write/admin, workspace read.\n"
    )
    workspace = typer.prompt("Bitbucket workspace slug (e.g. oss-mlops-platform)")
    choice = typer.prompt("Token type: 1) API token (email + token)  2) Workspace access token", type=int, default=1)
    auth_type = "api_token" if choice == 1 else "access_token"
    email = typer.prompt("Atlassian account email") if auth_type == "api_token" else ""
    token = typer.prompt("Token (input hidden)", hide_input=True)

    client = BitbucketClient(workspace, auth_type, token, email)
    try:
        client.check_workspace()
    except BitbucketError as e:
        typer.echo(f"Authentication failed: {e}")
        sys.exit(1)

    save_config({"workspace": workspace, "auth_type": auth_type, "email": email, "token": token})
    typer.echo(f"Authenticated. Configuration saved to {CONFIG_FILE} (permissions 600).")
    typer.echo("Tip: set BITBUCKET_API_TOKEN to override the stored token.")


if __name__ == "__main__":
    app()
