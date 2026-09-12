"""Hermetic regression: git stderr must not leak the GitHub access token.

run_claude_code_on_repo builds an authenticated clone URL by embedding the
user's token, and returned clone/push stderr verbatim in the tool response
message. git echoes the remote URL (including the token) on failure, so the
error path leaked the credential to users and logs.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def load():
    spec = importlib.util.spec_from_file_location(
        "claude_code_cli_under_test",
        Path(__file__).with_name("claude_code_cli.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TokenRedactionTests(unittest.TestCase):
    def setUp(self):
        self.module = load()

    def run_with_git(self, outputs):
        """Drive the function with a scripted sequence of git results."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return outputs[len(calls) - 1]

        with patch.object(self.module.subprocess, "run", side_effect=fake_run):
            return self.module.run_claude_code_on_repo(
                repo_url="https://github.com/o/r.git",
                feature_description="add a button",
                branch_name="b1",
                github_token="ghp_SECRET123",
                anthropic_key="sk-ant",
            ), calls

    def test_clone_failure_redacts_token(self):
        result, _ = self.run_with_git([
            Completed(returncode=128, stderr="fatal: could not read 'https://ghp_SECRET123@github.com/o/r.git'")
        ])
        self.assertFalse(result["success"])
        self.assertNotIn("ghp_SECRET123", result["message"])
        self.assertIn("***", result["message"])

    def test_push_failure_redacts_token(self):
        result, _ = self.run_with_git([
            Completed(),  # clone
            Completed(),  # checkout -b
            Completed(stdout=""),  # claude-code run
            Completed(stdout=""),  # git status --porcelain -> no changes
            Completed(stdout="HEAD branch: main"),  # remote show
            Completed(returncode=1, stderr="fatal: 'https://ghp_SECRET123@github.com/o/r.git' denied"),
        ])
        self.assertFalse(result["success"])
        self.assertNotIn("ghp_SECRET123", result["message"])

    def test_non_secret_stderr_passes_through(self):
        result, _ = self.run_with_git([
            Completed(returncode=128, stderr="fatal: repository not found")
        ])
        self.assertIn("repository not found", result["message"])

    def test_redact_helper_edges(self):
        redact = self.module._redact
        self.assertEqual(redact(None, "tok"), "")
        self.assertEqual(redact("no secret here", "tok"), "no secret here")
        self.assertEqual(redact("tok tok", "tok"), "*** ***")
        self.assertEqual(redact("anything", ""), "anything")


if __name__ == "__main__":
    unittest.main()
