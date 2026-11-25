"""Minimal Bitbucket Cloud REST API 2.0 client for the CLI tool.

Bitbucket has no official CLI (like `gh` / `glab`), so this talks to the REST
API directly. Nothing is persisted in .git/config: git credentials are passed
to child `git` processes through GIT_CONFIG_* environment variables.
"""
import base64
import json
import os
import re
import stat
import subprocess
import sys
import time
from urllib.parse import quote

import requests

API_BASE = "https://api.bitbucket.org/2.0"
CONFIG_FILE = os.path.expanduser("~/.bitbucket-cli-config.json")

# Username used for git-over-HTTPS together with each token type.
GIT_USER = {
    "api_token": "x-bitbucket-api-token-auth",
    "access_token": "x-token-auth",
    "oauth": "x-token-auth",
}
OAUTH_TOKEN_URL = "https://bitbucket.org/site/oauth2/access_token"


class BitbucketError(RuntimeError):
    pass


def slugify(name: str) -> str:
    """Bitbucket lowercases repo names and replaces odd characters with '-'."""
    return re.sub(r"[^a-z0-9._-]+", "-", name.lower()).strip("-")


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print("Bitbucket configuration not found. Please run 'configure_bitbucket.py' first.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict) -> None:
    fd = os.open(CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        json.dump(config, f)
    os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0600


class BitbucketClient:
    def __init__(
        self,
        workspace: str,
        auth_type: str,
        token: str,
        email: str = "",
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        expires_at: float = 0,
    ):
        if auth_type not in GIT_USER:
            raise ValueError(f"Unknown auth_type: {auth_type}")
        self.workspace = workspace
        self.auth_type = auth_type
        self.token = token
        self.email = email
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.expires_at = float(expires_at)
        self.session = requests.Session()
        if auth_type == "api_token":
            self.session.auth = (email, token)
        else:
            self.session.headers["Authorization"] = f"Bearer {token}"

    @classmethod
    def from_config(cls, workspace: str | None = None) -> "BitbucketClient":
        cfg = load_config()
        if cfg.get("auth_type") == "oauth":
            return cls.from_auth_config({**cfg, "workspace": workspace or cfg["workspace"]})
        token = os.environ.get("BITBUCKET_API_TOKEN") or cfg.get("token", "")
        if not token:
            print("No Bitbucket token found. Run 'configure_bitbucket.py' or set BITBUCKET_API_TOKEN.")
            sys.exit(1)
        cfg = {**cfg, "workspace": workspace or cfg["workspace"], "token": token}
        return cls.from_auth_config(cfg)

    @classmethod
    def from_auth_config(cls, config: dict) -> "BitbucketClient":
        return cls(
            config["workspace"],
            config["auth_type"],
            config.get("token", ""),
            config.get("email", ""),
            config.get("client_id", ""),
            config.get("client_secret", ""),
            config.get("refresh_token", ""),
            config.get("expires_at", 0),
        )

    def _refresh_oauth_token_if_needed(self) -> None:
        if self.auth_type != "oauth" or self.expires_at > time.time() + 60:
            return
        response = self.session.post(
            OAUTH_TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            timeout=60,
        )
        if response.status_code != 200:
            raise BitbucketError(f"OAuth token refresh failed ({response.status_code}): {response.text[:500]}")
        token_data = response.json()
        self.token = token_data["access_token"]
        self.refresh_token = token_data["refresh_token"]
        self.expires_at = time.time() + int(token_data["expires_in"])
        self.session.headers["Authorization"] = f"Bearer {self.token}"
        save_config(
            {
                "workspace": self.workspace,
                "auth_type": self.auth_type,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "token": self.token,
                "refresh_token": self.refresh_token,
                "expires_at": self.expires_at,
            }
        )

    # ---------- git credentials ----------
    def export_git_auth(self) -> None:
        """Make every child `git` process authenticate, without writing the token to disk."""
        self._refresh_oauth_token_if_needed()
        raw = f"{GIT_USER[self.auth_type]}:{self.token}".encode()
        header = "Authorization: Basic " + base64.b64encode(raw).decode()
        os.environ["GIT_CONFIG_COUNT"] = "1"
        os.environ["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        os.environ["GIT_CONFIG_VALUE_0"] = header
        os.environ["GIT_TERMINAL_PROMPT"] = "0"

    def clone_url(self, slug: str) -> str:
        return f"https://bitbucket.org/{self.workspace}/{slug}.git"

    # ---------- HTTP ----------
    def _request(self, method, path, ok=(200, 201, 202, 204), **kwargs):
        self._refresh_oauth_token_if_needed()
        if self.auth_type != "api_token":
            self.session.headers["Authorization"] = f"Bearer {self.token}"
        url = path if path.startswith("http") else f"{API_BASE}/{path.lstrip('/')}"
        resp = self.session.request(method, url, timeout=60, **kwargs)
        if resp.status_code not in ok:
            raise BitbucketError(f"{method} {url} -> {resp.status_code}: {resp.text[:500]}")
        return resp

    def _paginate(self, path):
        url = path
        while url:
            data = self._request("GET", url).json()
            yield from data.get("values", [])
            url = data.get("next")

    # ---------- workspace / repositories ----------
    def check_workspace(self) -> dict:
        return self._request("GET", f"workspaces/{self.workspace}").json()

    def check_git_access(self, repo_slug: str | None = None) -> bool:
        """Check Git read access using an existing repository, if one is available."""
        if repo_slug is None:
            repo = next(self._paginate(f"repositories/{self.workspace}?pagelen=1"), None)
            if repo is None:
                return False
            repo_slug = repo["slug"]

        self.export_git_auth()
        result = subprocess.run(
            ["git", "ls-remote", "--heads", self.clone_url(repo_slug)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise BitbucketError(
                f"Git read access check failed for {self.workspace}/{repo_slug}: "
                f"{detail or f'git exited with status {result.returncode}'}"
            )
        return True

    def get_repo(self, slug: str):
        resp = self._request("GET", f"repositories/{self.workspace}/{slug}", ok=(200, 403, 404))
        if resp.status_code == 403:
            if "Repository currently not available" in resp.text:
                return None
            raise BitbucketError(
                f"GET repository {self.workspace}/{slug} -> {resp.status_code}: {resp.text[:500]}"
            )
        return resp.json() if resp.status_code == 200 else None

    def create_repo(self, name: str, description: str = ""):
        body = {
            "scm": "git",
            "name": name,
            "description": description,
            "is_private": True,
            "fork_policy": "no_public_forks",  # private repo, forks allowed inside the workspace
        }
        return self._request("POST", f"repositories/{self.workspace}/{slugify(name)}", json=body).json()

    def fork_repo(self, source_slug: str, new_name: str):
        body = {"name": new_name, "workspace": {"slug": self.workspace}, "is_private": True}
        return self._request("POST", f"repositories/{self.workspace}/{source_slug}/forks", json=body).json()

    def set_default_branch(self, slug: str, branch: str) -> None:
        body = {"mainbranch": {"type": "branch", "name": branch}}
        self._request("PUT", f"repositories/{self.workspace}/{slug}", json=body)

    def enable_pipelines(self, slug: str) -> None:
        self._request("PUT", f"repositories/{self.workspace}/{slug}/pipelines_config", json={"enabled": True})

    # ---------- pipeline variables (workspace level = GitLab group variable) ----------
    def _var_path(self, repo_slug=None) -> str:
        if repo_slug:
            return f"repositories/{self.workspace}/{repo_slug}/pipelines_config/variables"
        return f"workspaces/{self.workspace}/pipelines-config/variables"

    def set_variable(self, key: str, value: str, secured: bool = False, repo_slug=None) -> None:
        """Create the variable, or update it if the key already exists."""
        base = self._var_path(repo_slug)
        body = {"key": key, "value": value, "secured": secured}
        for var in self._paginate(base):
            if var.get("key") == key:
                uuid = quote(var["uuid"], safe="")
                self._request("PUT", f"{base}/{uuid}", json=body)
                return
        self._request("POST", base, json=body)
