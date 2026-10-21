"""Hermetic unit tests for verify_deploy_ancestry.py (chip task_53b2277f).

Verifies commit SHA validation, GitHub compare API parsing, exit code conventions,
and local git fallback mechanisms without external network dependencies.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts import verify_deploy_ancestry as verifier

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


class TestVerifyDeployAncestryValidation(unittest.TestCase):
    """Test commit SHA validation rules."""

    def test_valid_sha(self):
        self.assertEqual(verifier.validate_sha(SHA_A, "release"), SHA_A)
        self.assertEqual(verifier.validate_sha(" " + SHA_B.upper() + " ", "contains"), SHA_B)

    def test_invalid_length(self):
        with self.assertRaises(verifier.AncestryError):
            verifier.validate_sha("a" * 39, "release")
        with self.assertRaises(verifier.AncestryError):
            verifier.validate_sha("a" * 41, "release")

    def test_invalid_hex_chars(self):
        with self.assertRaises(verifier.AncestryError):
            verifier.validate_sha("z" * 40, "contains")

    def test_zero_sentinel_rejected(self):
        with self.assertRaises(verifier.AncestryError):
            verifier.validate_sha("0" * 40, "release")


class TestVerifyDeployAncestryLogic(unittest.TestCase):
    """Test ancestry resolution logic across API and fallback layers."""

    def test_identity_case_avoids_network(self):
        with patch.object(verifier, "query_github_compare") as mock_api:
            result = verifier.verify_deploy_ancestry(
                release_sha=SHA_A,
                contains_sha=SHA_A,
            )
            mock_api.assert_not_called()
            self.assertTrue(result.is_ancestor)
            self.assertEqual(result.method, "identity")
            self.assertEqual(result.status, "identical")

    def test_api_ahead_is_ancestor(self):
        mock_payload = {
            "status": "ahead",
            "ahead_by": 5,
            "behind_by": 0,
        }
        with patch.object(verifier, "query_github_compare", return_value=mock_payload):
            result = verifier.verify_deploy_ancestry(
                release_sha=SHA_A,
                contains_sha=SHA_B,
            )
            self.assertTrue(result.is_ancestor)
            self.assertEqual(result.status, "ahead")
            self.assertEqual(result.ahead_by, 5)
            self.assertEqual(result.behind_by, 0)
            self.assertEqual(result.method, "github_api")

    def test_api_behind_is_not_ancestor(self):
        mock_payload = {
            "status": "behind",
            "ahead_by": 0,
            "behind_by": 3,
        }
        with patch.object(verifier, "query_github_compare", return_value=mock_payload):
            result = verifier.verify_deploy_ancestry(
                release_sha=SHA_A,
                contains_sha=SHA_B,
            )
            self.assertFalse(result.is_ancestor)
            self.assertEqual(result.status, "behind")
            self.assertEqual(result.behind_by, 3)

    def test_api_diverged_is_not_ancestor(self):
        mock_payload = {
            "status": "diverged",
            "ahead_by": 2,
            "behind_by": 2,
        }
        with patch.object(verifier, "query_github_compare", return_value=mock_payload):
            result = verifier.verify_deploy_ancestry(
                release_sha=SHA_A,
                contains_sha=SHA_B,
            )
            self.assertFalse(result.is_ancestor)
            self.assertEqual(result.status, "diverged")

    def test_api_failure_falls_back_to_git(self):
        with patch.object(verifier, "query_github_compare", side_effect=verifier.AncestryError("API failure")):
            with patch.object(verifier, "check_ancestry_via_git", return_value=True) as mock_git:
                result = verifier.verify_deploy_ancestry(
                    release_sha=SHA_A,
                    contains_sha=SHA_B,
                    allow_git_fallback=True,
                )
                mock_git.assert_called_once_with(SHA_B, SHA_A)
                self.assertTrue(result.is_ancestor)
                self.assertEqual(result.method, "git_merge_base")

    def test_api_failure_without_git_fallback_raises(self):
        with patch.object(verifier, "query_github_compare", side_effect=verifier.AncestryError("API failure")):
            with self.assertRaises(verifier.AncestryError):
                verifier.verify_deploy_ancestry(
                    release_sha=SHA_A,
                    contains_sha=SHA_B,
                    allow_git_fallback=False,
                )


class TestVerifyDeployAncestryCLI(unittest.TestCase):
    """Test CLI argument parsing and exit codes."""

    def test_cli_exit_zero_when_ancestor(self):
        mock_result = verifier.AncestryResult(
            is_ancestor=True,
            status="ahead",
            ahead_by=1,
            behind_by=0,
            release=SHA_A,
            contains=SHA_B,
            method="github_api",
            detail="verified",
        )
        with patch.object(verifier, "verify_deploy_ancestry", return_value=mock_result):
            code = verifier.main(["--release", SHA_A, "--contains", SHA_B, "--quiet"])
            self.assertEqual(code, 0)

    def test_cli_exit_one_when_not_ancestor(self):
        mock_result = verifier.AncestryResult(
            is_ancestor=False,
            status="behind",
            ahead_by=0,
            behind_by=1,
            release=SHA_A,
            contains=SHA_B,
            method="github_api",
            detail="failed",
        )
        with patch.object(verifier, "verify_deploy_ancestry", return_value=mock_result):
            code = verifier.main(["--release", SHA_A, "--contains", SHA_B, "--quiet"])
            self.assertEqual(code, 1)

    def test_cli_exit_two_on_invalid_sha(self):
        code = verifier.main(["--release", "invalid-sha", "--contains", SHA_B, "--quiet"])
        self.assertEqual(code, 2)

    def test_cli_json_output(self):
        mock_result = verifier.AncestryResult(
            is_ancestor=True,
            status="ahead",
            ahead_by=3,
            behind_by=0,
            release=SHA_A,
            contains=SHA_B,
            method="github_api",
            detail="Release A contains B",
        )
        with patch.object(verifier, "verify_deploy_ancestry", return_value=mock_result):
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                code = verifier.main(["--release", SHA_A, "--contains", SHA_B, "--json"])
                self.assertEqual(code, 0)
                data = json.loads(mock_stdout.getvalue())
                self.assertTrue(data["is_ancestor"])
                self.assertEqual(data["ahead_by"], 3)
                self.assertEqual(data["behind_by"], 0)


if __name__ == "__main__":
    unittest.main()
