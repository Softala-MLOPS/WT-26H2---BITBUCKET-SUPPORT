# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer",
#     "requests",
# ]
# ///
import os
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import requests
import typer

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "bitbucket"))
from bitbucket_client import CONFIG_FILE, BitbucketClient, BitbucketError, save_config  # noqa: E402

app = typer.Typer()
OAUTH_AUTHORIZE_URL = "https://bitbucket.org/site/oauth2/authorize"
OAUTH_TOKEN_URL = "https://bitbucket.org/site/oauth2/access_token"
DEFAULT_CALLBACK_URL = "http://127.0.0.1:8765/callback"
OAUTH_SETUP_DOCS_URL = "https://support.atlassian.com/bitbucket-cloud/docs/use-oauth-on-bitbucket-cloud/"


@app.command()
def main():
    """Configure Bitbucket Cloud authentication."""
    typer.echo("Configuring Bitbucket Cloud authentication...")
    workspace = typer.prompt("Bitbucket workspace slug (e.g. oss-mlops-platform)")
    if os.path.exists(CONFIG_FILE) and reuse_saved_auth(workspace):
        return

    auth_choice = typer.prompt("Authentication: 1) Browser (OAuth)  2) Token", type=int, default=1)
    if auth_choice == 1:
        config = configure_oauth(workspace)
    elif auth_choice == 2:
        config = configure_token(workspace)
    else:
        typer.echo("Invalid authentication choice.")
        raise typer.Exit(1)

    client = BitbucketClient.from_auth_config(config)
    try:
        client.check_workspace()
        client.check_git_access()
    except BitbucketError as e:
        typer.echo(f"Authentication failed: {e}")
        raise typer.Exit(1) from e

    save_config(config)
    typer.echo(f"Authenticated. Configuration saved to {CONFIG_FILE} (permissions 600).")
    if config["auth_type"] != "oauth":
        typer.echo("Tip: set BITBUCKET_API_TOKEN to override the stored token.")


def reuse_saved_auth(workspace: str) -> bool:
    """Return whether a valid saved login should be reused without re-authentication."""
    client = BitbucketClient.from_config(workspace)
    try:
        client.check_workspace()
        if not client.check_git_access():
            typer.echo("No existing repository found; Git access will be checked when a repository is created.")
    except BitbucketError as error:
        typer.echo(f"Saved Bitbucket authentication cannot be reused: {error}")
        return False

    typer.echo(f"Already authenticated to Bitbucket workspace '{workspace}'.")
    return not typer.confirm("Do you want to re-authenticate?", default=False)


def configure_token(workspace: str) -> dict:
    typer.echo(
        "Use an Atlassian API token (account email + token) or a workspace access token.\n"
        "For a workspace access token, enable Pipelines > Edit variables (pipeline:variable),\n"
        "as well as the repository, project, and workspace permissions needed by this tool.\n"
        "Workspace access token permissions cannot be changed after creation; create a new token if a scope is missing.\n"
    )
    choice = typer.prompt("Token type: 1) API token (email + token)  2) Workspace access token", type=int, default=1)
    if choice not in (1, 2):
        typer.echo("Invalid token type.")
        raise typer.Exit(1)
    auth_type = "api_token" if choice == 1 else "access_token"
    email = typer.prompt("Atlassian account email") if auth_type == "api_token" else ""
    token = typer.prompt("Token (input hidden)", hide_input=True)
    return {
        "workspace": workspace,
        "auth_type": auth_type,
        "email": email,
        "token": token,
    }


def configure_oauth(workspace: str) -> dict:
    typer.echo(
        "Create an OAuth consumer in your Bitbucket workspace first.\n"
        f"Official instructions: {OAUTH_SETUP_DOCS_URL}\n"
        f"Open workspace '{workspace}' > Settings > Workspace settings > Apps and features > OAuth consumers.\n"
        "Suggested consumer name: OSS MLOps Repository Setup Tool (this name appears in the authorization screen).\n"
        "On the Scopes tab, enable Pipelines > Edit variables (pipeline:variable), plus the repository,\n"
        "project, and workspace permissions needed by this tool.\n"
        f"Register this callback URL in the consumer: {DEFAULT_CALLBACK_URL}\n"
        "When prompted for the callback URL below, press Enter to use it."
    )
    client_id = typer.prompt("OAuth Client ID")
    client_secret = typer.prompt("OAuth consumer secret", hide_input=True)
    callback_url = typer.prompt(
        "Registered OAuth callback URL (press Enter to use the default)",
        default=DEFAULT_CALLBACK_URL,
    )
    parsed_callback = urlsplit(callback_url)
    try:
        port = parsed_callback.port
    except ValueError:
        port = None
    if (
        parsed_callback.scheme != "http"
        or parsed_callback.hostname != "127.0.0.1"
        or parsed_callback.path != "/callback"
        or parsed_callback.query
        or parsed_callback.fragment
        or port is None
        or not 1 <= port <= 65535
    ):
        typer.echo("Callback URL must be a local URL such as http://127.0.0.1:8765/callback.")
        raise typer.Exit(1)

    state = secrets.token_urlsafe(32)
    authorization_url = f"{OAUTH_AUTHORIZE_URL}?{urlencode({'client_id': client_id, 'response_type': 'code', 'state': state})}"
    callback_result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            received_state = query.get("state", [""])[0]
            if self.path.split("?", 1)[0] == parsed_callback.path and secrets.compare_digest(received_state, state):
                callback_result.update(
                    code=query.get("code", [""])[0],
                    error=query.get("error", [""])[0],
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Bitbucket authorization received. You can close this window.")
            else:
                self.send_error(400)

        def log_message(self, format, *args):
            return

    try:
        server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    except OSError as e:
        typer.echo(f"Could not listen on callback port {port}: {e}")
        raise typer.Exit(1) from e

    server.timeout = 1
    typer.echo(f"Opening Bitbucket authorization in your browser:\n{authorization_url}")
    webbrowser.open(authorization_url)
    typer.echo("If the browser did not open, copy the URL above. Waiting for authorization (5 minutes)...")
    deadline = time.monotonic() + 300
    try:
        while not callback_result and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if not callback_result:
        typer.echo("Timed out waiting for Bitbucket authorization.")
        raise typer.Exit(1)
    if callback_result.get("error"):
        typer.echo(f"Bitbucket authorization was denied: {callback_result['error']}")
        raise typer.Exit(1)
    if not callback_result.get("code"):
        typer.echo("Bitbucket did not return an authorization code.")
        raise typer.Exit(1)

    response = requests.post(
        OAUTH_TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "authorization_code", "code": callback_result["code"]},
        timeout=60,
    )
    if response.status_code != 200:
        raise BitbucketError(f"OAuth token exchange failed ({response.status_code}): {response.text[:500]}")
    token_data = response.json()
    return {
        "workspace": workspace,
        "auth_type": "oauth",
        "client_id": client_id,
        "client_secret": client_secret,
        "token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": time.time() + int(token_data["expires_in"]),
    }


if __name__ == "__main__":
    app()
