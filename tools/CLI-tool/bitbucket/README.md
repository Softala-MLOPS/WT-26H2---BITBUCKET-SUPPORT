# Bitbucket support

Adds Bitbucket Cloud next to GitHub and GitLab. Pick **3) Bitbucket** in `create_gitrepo_devops_for_ml_work.sh`;
the "organization name" is the Bitbucket **workspace slug**.

| Part | File |
|---|---|
| Auth (browser OAuth, API token, or workspace access token) | `../configure_bitbucket.py` |
| REST client (create, fork, variables, pipelines) | `bitbucket_client.py` |
| Config repo + branches + variables | `create_config_repo.py` |
| Working repo (fork) | `create_working_repo.py` |
| Self-hosted runner | `install_local_runner.sh` |
| CI/CD | `../files/bitbucket/<env>/bitbucket-pipelines.yml` |

Notes
- The setup is not tied to a specific developer: each person running it supplies the target workspace slug and authenticates with credentials they are authorized to use there. Each person should use their own Atlassian API token/OAuth authorization; a workspace access token or shared OAuth consumer credentials should only be used when the workspace administrator intentionally provides them. Never commit or share tokens, OAuth secrets, or the local config file.
- `configure_bitbucket.py` supports browser OAuth and token authentication. For OAuth, create an OAuth consumer in the workspace with **Pipelines > Edit variables** (`pipeline:variable`) plus the repository, project, and workspace permissions needed by the tool. Register `http://127.0.0.1:8765/callback` as its callback URL; the setup opens the authorization page and waits for the local callback. The OAuth access and refresh tokens and consumer credentials are stored in `~/.bitbucket-cli-config.json` with owner-only permissions; access tokens are refreshed automatically.
- Token authentication still supports Atlassian API tokens (email + token) and workspace access tokens. Workspace access tokens must include **Pipelines > Edit variables** (`pipeline:variable`) to create/update workspace Pipelines variables; this scope cannot be added to an existing token, so create a replacement token if it was omitted.
- A saved Bitbucket login is checked and reused on later runs; re-authentication is only needed if the saved credentials no longer work or the user requests it.
- Config variables are stored as **workspace** Pipelines variables (GitLab: group variables). The SSH key is stored base64 encoded as `REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64`.
- `development` runs on a self-hosted Linux Shell runner (`self.hosted`, `linux.shell`); `staging`/`production` run on Bitbucket cloud runners.
- Git credentials are passed through `GIT_CONFIG_*` environment variables and never written to `.git/config`.
- Needs git >= 2.31.
