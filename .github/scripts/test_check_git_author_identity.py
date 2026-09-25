#!/usr/bin/env python3
"""Behavioral coverage for the Git author-identity fixture guard."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "check_git_author_identity", SCRIPT_DIR / "check_git_author_identity.py"
)
assert SPEC and SPEC.loader
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


class GitAuthorIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git("init", "-q")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            env=CHECKER.clean_git_env(),
        )
        if check and result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout or args)
        return result

    def commit(self, message: str, *, name: str, email: str) -> str:
        self.git("-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "--allow-empty", "-qm", message)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def test_reserved_test_tld_is_a_fixture(self) -> None:
        self.assertIsNotNone(CHECKER.fixture_reason("Someone", "ratchet-test@example.invalid"))
        self.assertIsNotNone(CHECKER.fixture_reason("Ratchet Test", "person@company.com"))
        self.assertIsNone(CHECKER.fixture_reason("David Zhang", "david.d.zhang@gmail.com"))
        self.assertIsNone(CHECKER.fixture_reason("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com"))

    def test_rejects_an_address_whose_domain_cannot_resolve(self) -> None:
        """PR #12239: `r <r@r>` authored 66 commits and this guard passed all of them.

        It is not a fixture by name and carries no reserved TLD, so every
        enumerated rule missed it. What makes it wrong is that `r` cannot be a
        registrable domain, so the address can never be delivered or attributed.
        """
        self.assertIsNone(CHECKER.fixture_reason("r", "r@r"))
        self.assertIsNotNone(CHECKER.rejection_reason("r", "r@r"))
        self.assertIsNotNone(CHECKER.rejection_reason("x", "x@x"))

    def test_keeps_real_addresses_including_github_noreply(self) -> None:
        for email in (
            "david.d.zhang@gmail.com",
            "git-on-my-level@users.noreply.github.com",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ):
            self.assertIsNone(CHECKER.rejection_reason("Someone", email), email)

    def test_a_name_only_identity_is_not_judged_on_its_absent_email(self) -> None:
        """`local_config_identities` emits user.name with an empty email; that is
        an absent address, not an undeliverable one, and must not fail on its own."""
        self.assertIsNone(CHECKER.rejection_reason("David Zhang", ""))

    def test_rejects_a_repo_local_unroutable_override(self) -> None:
        """The clone-local override is the mechanism both incidents shared."""
        self.git("config", "--local", "user.email", "r@r")
        self.git("config", "--local", "user.name", "r")
        failures = CHECKER.failures_for(CHECKER.local_config_identities(self.root))
        self.assertTrue(failures)
        self.assertTrue(any("local-config" in item and "r@r" in item for item in failures))

    def test_rejects_unroutable_authors_in_the_commit_range(self) -> None:
        """The CI lane never sees the clone's config, so the commit range is the
        only unbypassable place this can be caught."""
        base = self.commit("seed", name="David Zhang", email="david.d.zhang@gmail.com")
        self.commit("bad", name="r", email="r@r")
        failures = CHECKER.failures_for(CHECKER.range_identities(self.root, base, "HEAD"))
        self.assertTrue(failures)
        self.assertTrue(any("r@r" in item for item in failures))

    def test_rejects_a_repo_local_fixture_override(self) -> None:
        self.git("config", "--local", "user.email", "ratchet-test@example.invalid")
        self.git("config", "--local", "user.name", "Ratchet Test")
        failures = CHECKER.failures_for(CHECKER.local_config_identities(self.root))
        self.assertTrue(failures)
        self.assertTrue(any("local-config" in item and "example.invalid" in item for item in failures))

    def test_rejects_fixture_authors_in_the_commit_range(self) -> None:
        base = self.commit("seed", name="David Zhang", email="david.d.zhang@gmail.com")
        self.commit("bad", name="Ratchet Test", email="ratchet-test@example.invalid")
        failures = CHECKER.failures_for(CHECKER.range_identities(self.root, base, "HEAD"))
        self.assertTrue(failures)
        self.assertTrue(any("Ratchet Test" in item for item in failures))

    def test_accepts_a_human_author_without_local_override(self) -> None:
        base = self.commit("seed", name="David Zhang", email="david.d.zhang@gmail.com")
        self.commit("good", name="David Zhang", email="david.d.zhang@gmail.com")
        failures = CHECKER.failures_for(
            CHECKER.local_config_identities(self.root) + CHECKER.range_identities(self.root, base, "HEAD")
        )
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
