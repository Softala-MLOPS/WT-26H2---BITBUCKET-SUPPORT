# CLI Tool for ML Project Repository Management
This CLI tool automates the creation, configuration and management of configuration and working repositories for MLOps usage on GitHub, GitLab, and Bitbucket. It includes two modules:

1. **Repository Setup Module:** Automates repository creation, branch setup, and configuration
2. **Repository Forking Module:** Fetches repository details and forks them under a specified organization

![MLOPS tool project diagram](../resources/diagrams/MLOPSDiagram.png)

## Current limitations and requirements

- The tool runs in Unix command-line environments: macOS or Linux (WSL for Windows)
- GitHub authentication uses a token and HTTPS instead of SSH for the `gh` CLI
	- https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-personal-access-token-classic
	- https://docs.github.com/en/get-started/getting-started-with-git/caching-your-github-credentials-in-git?platform=linux
 	- Using the copy code from commandline into GitHub's site should work also
- **GitHub only:** A sufficiently new `gh` version is needed to fork and rename the working repository (tested with 2.45.0).
- GitHub secrets are currently set up at organization level. This means that you may need separate GitHub organizations for different ML setups.
- GitLab variables are set up at group level; Bitbucket Pipelines variables are set up at workspace level.
- Python virtual environments may interfere with GitHub actions runner. (No defined solution for this at the moment)
	- Usage of Python virtual environments is still recommended
- Platform-specific setup requires interacting with the hosting service:
    - Setting up the organizations, groups, or workspaces
    - Enabling the repository's CI/CD feature
    - Setting up a self-hosted runner where required (GitHub/GitLab; Bitbucket development)
    - Setting up the SSH secret for remote cluster access

## Features

### Repository Setup Module

- Create a new repository in a specified organization, group, or workspace
- Clone the repository and initialize it with predefined branches: `development`, `staging`, and `production`
- Copy branch-specific files for different environments
- Set up platform variables/secrets using a configuration file (`config.yaml`)
- Set the development branch as the default branch

### Repository Forking Module

- Fetch repository details
- Fork an existing repository under a specified organization with a unique name

## Prerequisites

- For the local installation of the MLOPS platform you need a computer with 16GB RAM with 10GB allocated for Docker to use
	- There is a possibility to use remote virtual machines for the "local installation" of the platform
 	- [Generic remote server installation](./Generic%20guide%20to%20start%20a%20remote%20server.md)
  	- [CSC specific remote server installation](./CSC%20user%20guide.md)
- For Windows machines you also need Linux distro installed via WSL
	- Linux distro should be quite new for Python 3.11 and GitHub CLI 2.45.0
 	- Tested with Ubuntu 24 LTS

## Usage

- You can find more detailed installation and setup guide here: [Installations, setups and usage.md](./Installations,%20setups%20and%20usage.md)
