"""Read-only GCP identity helpers for the finops pulls.

Two identities are used, on purpose:

  * ``read-only-bot-account@based-hardware.iam.gserviceaccount.com`` for every READ
    (BigQuery billing export, Firestore projections). Sourced from
    ``~/.hermes/scripts/omi-prod-gcp-read-only-env.sh``. The documented
    ``~/.hermes/profiles`` path does not exist on this host and falls through
    silently to owner credentials, so the account is verified after sourcing.
  * the interactive owner account for BigQuery WRITES into ``omi_finops``
    (dataset/table create, partition replace). Verified by name before any write.

Nothing here prints or persists a token.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

READONLY_ENV = os.path.expanduser("~/.hermes/scripts/omi-prod-gcp-read-only-env.sh")
READONLY_ACCOUNT = "read-only-bot-account@based-hardware.iam.gserviceaccount.com"
WRITER_ACCOUNT = "david@scalingforever.com"
PROJECT = "based-hardware"


def _sh(cmd: str, timeout: int = 180) -> str:
    p = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("command failed (%d): %s" % (p.returncode, p.stderr[-400:]))
    return p.stdout.strip()


def readonly_account() -> str:
    """Account that the read-only env script actually activates."""
    return _sh('source "%s" >/dev/null 2>&1; gcloud config get-value account 2>/dev/null' % READONLY_ENV)


def assert_readonly_identity() -> str:
    acct = readonly_account()
    if acct != READONLY_ACCOUNT:
        raise SystemExit(
            "read-only identity check failed: got %r, expected %r. "
            "The env script fell through to owner credentials; refusing to pull." % (acct, READONLY_ACCOUNT)
        )
    return acct


def assert_writer_identity() -> str:
    """The active (non-sourced) gcloud account, which is what `bq load` will use."""
    acct = _sh("gcloud config get-value account 2>/dev/null")
    if acct != WRITER_ACCOUNT:
        raise SystemExit(
            "BigQuery writer identity check failed: got %r, expected %r. "
            "Refusing to write to omi_finops." % (acct, WRITER_ACCOUNT)
        )
    return acct


class Token:
    """Access token for the read-only bot, refreshed lazily (they expire in ~60 min)."""

    TTL = 30 * 60

    def __init__(self) -> None:
        self._value = ""
        self._at = 0.0

    def get(self, force: bool = False) -> str:
        if force or not self._value or (time.time() - self._at) > self.TTL:
            self._value = _sh('source "%s" >/dev/null 2>&1; gcloud auth print-access-token' % READONLY_ENV)
            if not self._value:
                raise RuntimeError("empty access token from the read-only profile")
            self._at = time.time()
        return self._value


TOKEN = Token()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "read"
    if which == "read":
        print(assert_readonly_identity())
    else:
        print(assert_writer_identity())
