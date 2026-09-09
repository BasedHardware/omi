"""Read-only GCP identity helpers for the finops pulls.

Two identities are used, on purpose:

  * ``read-only-bot-account@based-hardware.iam.gserviceaccount.com`` for every READ
    (BigQuery billing export, Firestore projections). Sourced from
    ``~/.hermes/scripts/omi-prod-gcp-read-only-env.sh``. The documented
    ``~/.hermes/profiles`` path does not exist on this host and falls through
    silently to owner credentials, so the account is verified after sourcing.
  * ``finops-writer@based-hardware.iam.gserviceaccount.com`` for BigQuery WRITES
    into ``omi_finops`` only. Key at
    ``~/.hermes/credentials/omi-gcp/prod/finops-writer-key.json``. Human ADC
    expires; the read-only bot must stay read-only.

Nothing here prints or persists a token.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

READONLY_ENV = os.path.expanduser("~/.hermes/scripts/omi-prod-gcp-read-only-env.sh")
READONLY_ACCOUNT = "read-only-bot-account@based-hardware.iam.gserviceaccount.com"
WRITER_KEY = os.path.expanduser("~/.hermes/credentials/omi-gcp/prod/finops-writer-key.json")
WRITER_GCLOUD = os.path.expanduser("~/.hermes/gcloud/omi-finops-writer")
WRITER_ACCOUNT = "finops-writer@based-hardware.iam.gserviceaccount.com"
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


def apply_writer_env() -> None:
    """Point this process at the finops-writer key so subsequent `bq` calls use it."""
    if not os.path.isfile(WRITER_KEY):
        raise SystemExit("writer key missing: %s" % WRITER_KEY)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = WRITER_KEY
    os.environ["CLOUDSDK_CONFIG"] = WRITER_GCLOUD
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT
    os.environ["GCLOUD_PROJECT"] = PROJECT
    os.environ["CLOUDSDK_CORE_PROJECT"] = PROJECT
    os.environ["CLOUDSDK_PROJECT"] = PROJECT
    os.environ["CLOUDSDK_PYTHON"] = os.environ.get("CLOUDSDK_PYTHON") or os.path.expanduser("~/.local/bin/python3.11")
    os.environ["PYTHONPATH"] = ""
    os.environ.pop("CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT", None)


def assert_writer_identity() -> str:
    """The finops-writer SA, which is what `bq load` will use."""
    apply_writer_env()
    p = subprocess.run(
        ["gcloud", "config", "get-value", "account"],
        capture_output=True,
        text=True,
        env=os.environ,
    )
    acct = (p.stdout or "").strip()
    if p.returncode != 0 or acct != WRITER_ACCOUNT:
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
