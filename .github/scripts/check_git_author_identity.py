#!/usr/bin/env python3
"""Reject unattributable Git identities on real commits and repo-local config.

PR #11525's commits were minted as ``Ratchet Test <ratchet-test@example.invalid>``
because a leftover ``user.email`` in the clone's ``.git/config`` overrode the
global identity. GitHub maps avatars by author email, so those commits did not
belong to the person who opened the PR.

PR #12239 hit the same failure with a different value: a clone-local
``r <r@r>`` authored 66 commits over five days, and this guard passed every one
of them. It was enumerating the previous incident's literal fixture name and
reserved TLDs, so an address that was merely impossible slipped straight
through. The rule is now the property that actually matters — an address whose
domain cannot resolve can never be attributed to anyone, whatever it is called.

Fixture identities belong only in temporary test repositories. Never write
``user.name`` / ``user.email`` into this clone's local config.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from email.utils import parseaddr
from pathlib import Path
from typing import NamedTuple

_GIT_ENV_SCRUB = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_QUARANTINE_PATH",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
}

RESERVED_TEST_TLDS = frozenset({"invalid", "test", "localhost"})
FIXTURE_NAMES = frozenset({"ratchet test"})
FIXTURE_LOCAL_PARTS = frozenset({"ratchet-test"})


class Identity(NamedTuple):
    kind: str
    name: str
    email: str
    detail: str


def clean_git_env(source: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    for key in _GIT_ENV_SCRUB:
        env.pop(key, None)
    return env


def run_git(root: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=None if root is None else root,
        check=False,
        capture_output=True,
        text=True,
        env=clean_git_env(),
    )


def parse_ident(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if "<" in value:
        value = value.split(">", 1)[0] + ">"
    name, email = parseaddr(value)
    return name.strip(), email.strip().lower()


def email_tld(email: str) -> str:
    if "@" not in email:
        return ""
    domain = email.rsplit("@", 1)[1]
    if "." not in domain:
        return domain
    return domain.rsplit(".", 1)[1]


def fixture_reason(name: str, email: str) -> str | None:
    normalized_name = " ".join(name.lower().split())
    local_part = email.split("@", 1)[0] if email else ""
    tld = email_tld(email)
    if tld in RESERVED_TEST_TLDS:
        return f"reserved test TLD .{tld}"
    if normalized_name in FIXTURE_NAMES:
        return "fixture display name"
    if local_part in FIXTURE_LOCAL_PARTS:
        return "fixture local-part"
    return None


def undeliverable_reason(email: str) -> str | None:
    """Why this address can never reach anyone, or None if it might.

    Deliberately weaker than "is this a real mailbox" — that is not decidable
    here. It rejects only addresses that are impossible under any DNS: no ``@``,
    an empty domain, or a domain with no dot, which cannot be a registrable
    name. ``r@r`` is the whole reason this exists. A real address, including a
    GitHub ``users.noreply.github.com`` one, always passes.
    """
    if not email:
        return None
    if "@" not in email:
        return "no @ in the address"
    domain = email.rsplit("@", 1)[1]
    if not domain:
        return "empty domain"
    if "." not in domain:
        return f"domain '{domain}' has no dot, so it can never resolve"
    return None


def rejection_reason(name: str, email: str) -> str | None:
    """Why this identity must never author a commit, or None if it may."""
    return fixture_reason(name, email) or undeliverable_reason(email)


def local_config_identities(root: Path | None) -> list[Identity]:
    identities: list[Identity] = []
    for key in ("user.name", "user.email"):
        result = run_git(root, "config", "--local", "--get", key)
        if result.returncode != 0:
            continue
        value = result.stdout.strip()
        if not value:
            continue
        if key == "user.name":
            identities.append(Identity("local-config", value, "", key))
        else:
            identities.append(Identity("local-config", "", value, key))
    return identities


def pending_identities(root: Path | None) -> list[Identity]:
    identities: list[Identity] = []
    for var, kind in (("GIT_AUTHOR_IDENT", "pending-author"), ("GIT_COMMITTER_IDENT", "pending-committer")):
        result = run_git(root, "var", var)
        if result.returncode != 0 or not result.stdout.strip():
            continue
        name, email = parse_ident(result.stdout)
        identities.append(Identity(kind, name, email, var))
    return identities


def range_identities(root: Path | None, base: str, head: str) -> list[Identity]:
    result = run_git(root, "log", f"{base}..{head}", "--format=%H%x09%an%x09%ae%x09%cn%x09%ce")
    if result.returncode != 0:
        return []
    identities: list[Identity] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, author_name, author_email, committer_name, committer_email = line.split("\t", 4)
        identities.append(Identity("author", author_name, author_email, sha))
        identities.append(Identity("committer", committer_name, committer_email, sha))
    return identities


def failures_for(identities: list[Identity]) -> list[str]:
    failures: list[str] = []
    for identity in identities:
        reason = rejection_reason(identity.name, identity.email)
        if reason is None:
            continue
        who = identity.name or identity.email or "(empty)"
        if identity.email and identity.name:
            who = f"{identity.name} <{identity.email}>"
        elif identity.email:
            who = identity.email
        failures.append(f"{identity.kind} {who} on {identity.detail} ({reason})")
    return failures


def report(failures: list[str]) -> int:
    if not failures:
        print("OK: Git author identity is attributable.")
        return 0
    print("FAIL: unattributable Git identity would mint commits owned by nobody.", file=sys.stderr)
    for failure in failures:
        print(f"- {failure}", file=sys.stderr)
    print(
        "Unset a leftover clone override with: "
        "git config --local --unset-all user.email; git config --local --unset-all user.name",
        file=sys.stderr,
    )
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root (default: current directory)")
    parser.add_argument("--base", help="Exclusive start of the commit range to inspect")
    parser.add_argument("--head", default="HEAD", help="Inclusive end of the commit range")
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Inspect the identity the next commit would use (pre-commit)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve() if args.root else None
    identities = local_config_identities(root)
    if args.pending:
        identities.extend(pending_identities(root))
    if args.base:
        identities.extend(range_identities(root, args.base, args.head))
    return report(failures_for(identities))


if __name__ == "__main__":
    raise SystemExit(main())
