import sys
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

CLI_TOOL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLI_TOOL_DIR))

import configure_bitbucket
from bitbucket_client import BitbucketClient, BitbucketError


class BitbucketGitAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = BitbucketClient("workspace", "api_token", "token", email="user@example.com")

    @patch.object(BitbucketClient, "export_git_auth")
    @patch("bitbucket_client.subprocess.run")
    def test_check_git_access_skips_empty_workspace(self, run, export_git_auth):
        self.client._paginate = lambda path: iter([])

        self.assertFalse(self.client.check_git_access())

        export_git_auth.assert_not_called()
        run.assert_not_called()

    @patch.object(BitbucketClient, "export_git_auth")
    @patch("bitbucket_client.subprocess.run")
    def test_check_git_access_uses_existing_repository(self, run, export_git_auth):
        self.client._paginate = lambda path: iter([{"slug": "existing-repo"}])
        run.return_value = CompletedProcess([], 0, stdout="", stderr="")

        self.assertTrue(self.client.check_git_access())

        export_git_auth.assert_called_once_with()
        run.assert_called_once_with(
            ["git", "ls-remote", "--heads", "https://bitbucket.org/workspace/existing-repo.git"],
            capture_output=True,
            text=True,
        )

    @patch.object(BitbucketClient, "export_git_auth")
    @patch("bitbucket_client.subprocess.run")
    def test_check_git_access_reports_git_permission_failure(self, run, _export_git_auth):
        run.return_value = CompletedProcess([], 128, stdout="", stderr="HTTP 403")

        with self.assertRaisesRegex(BitbucketError, "Git read access check failed.*HTTP 403"):
            self.client.check_git_access("new-repo")

    @patch("configure_bitbucket.typer.confirm", return_value=False)
    @patch("configure_bitbucket.typer.echo")
    @patch("configure_bitbucket.BitbucketClient.from_config")
    @patch("configure_bitbucket.os.path.exists", return_value=True)
    def test_saved_auth_with_git_failure_requests_reauthentication(
        self, _exists, from_config, _echo, _confirm
    ):
        client = from_config.return_value
        client.check_git_access.side_effect = BitbucketError("HTTP 403")

        self.assertFalse(configure_bitbucket.reuse_saved_auth("workspace"))
        client.check_workspace.assert_called_once_with()
        client.check_git_access.assert_called_once_with()

    @patch("configure_bitbucket.typer.confirm", return_value=False)
    @patch("configure_bitbucket.typer.echo")
    @patch("configure_bitbucket.BitbucketClient.from_config")
    @patch("configure_bitbucket.os.path.exists", return_value=True)
    def test_saved_auth_with_git_access_is_reused(
        self, _exists, from_config, _echo, _confirm
    ):
        client = from_config.return_value

        self.assertTrue(configure_bitbucket.reuse_saved_auth("workspace"))
        client.check_workspace.assert_called_once_with()
        client.check_git_access.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
