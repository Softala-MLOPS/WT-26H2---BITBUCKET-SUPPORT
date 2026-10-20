# Bitbucket support

Adds Bitbucket Cloud next to GitHub and GitLab. Pick **3) Bitbucket** in `create_gitrepo_devops_for_ml_work.sh`;
the "organization name" is the Bitbucket **workspace slug**.

| Part | File |
|---|---|
| Auth (API token or workspace access token) | `../configure_bitbucket.py` |
| REST client (create, fork, variables, pipelines) | `bitbucket_client.py` |
| Config repo + branches + variables | `create_config_repo.py` |
| Working repo (fork) | `create_working_repo.py` |
| Self-hosted runner | `install_local_runner.sh` |
| CI/CD | `../files/bitbucket/<env>/bitbucket-pipelines.yml` |

Notes
- Config variables are stored as **workspace** Pipelines variables (GitLab: group variables). The SSH key is stored base64 encoded as `REMOTE_CLUSTER_SSH_PRIVATE_KEY_B64`.
- `development` runs on a self-hosted Linux Shell runner (`self.hosted`, `linux.shell`); `staging`/`production` run on Bitbucket cloud runners.
- Git credentials are passed through `GIT_CONFIG_*` environment variables and never written to `.git/config`.
- Needs git >= 2.31.
