"""Cloud Run identity layer for the finops job.

Replaces the laptop cron identity plumbing (``gcpauth.py``) when the job runs as a
Cloud Run Job:

  * every READ and every WRITE runs under the job's runtime service account via
    Application Default Credentials (``google.auth.default()``). No env script to
    source, no ``gcloud`` subprocess, no JSON key on disk, no ``CLOUDSDK_CONFIG``.
  * optional file-mounted secrets (Cloud Run ``--set-secrets`` volume mounts) are
    read from ``FINOPS_SECRETS_DIR`` (default ``/run/secrets/finops``) by file NAME.
    The loader only returns values to callers; nothing is printed or logged.

Identity expectations (verified at startup by ``assert_runtime_identity``):

  * the job's runtime SA is the *writer*: ``finops-writer@based-hardware`` (or the
    approved runtime replacement pinned in ``FINOPS_WRITER_SA``). It holds the
    dataset-scoped BigQuery write grants that ``finops-writer`` has today.
  * read scopes (billing export, Firestore projections) are granted to the same
    runtime SA; the separate laptop read-only bot is NOT used on Cloud Run.

Local cron keeps using ``gcpauth.py`` unchanged; this module is imported by the
Cloud Run path only (see ``run_unit_cost.py --auth cloudrun``).
"""

from __future__ import annotations

import json
import os
import pathlib

PROJECT = "based-hardware"
DATASET = "omi_finops"

WRITER_SA_DEFAULT = "finops-writer@based-hardware.iam.gserviceaccount.com"
RUNTIME_PROJECT_DEFAULT = PROJECT

# File-mounted secrets live here (Cloud Run Job volume mount); read lazily so the
# mount point can be redirected in tests/preflight.
DEFAULT_SECRETS_DIR = "/run/secrets/finops"


def secrets_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("FINOPS_SECRETS_DIR", DEFAULT_SECRETS_DIR))


# Secret file names this job understands. Values are never printed.
SECRET_FILES = {
    "prometheus": "OMI_PROMETHEUS_TOKEN",
    "stripe": "STRIPE_API_KEY",
    "openai": "OPENAI_ADMIN_KEY",
    "anthropic": "ANTHROPIC_ADMIN_API_KEY",
    "posthog": "MCP_POSTHOG_API_KEY",
}


class AuthError(SystemExit):
    """Raised (as SystemExit for uniform CLI failure) when identity checks fail."""


def _credentials():
    """ADC credentials via google-auth. Fails loudly when none are present."""
    try:
        import google.auth
    except ImportError as e:  # pragma: no cover - image always ships google-auth
        raise AuthError("google-auth is not installed in this environment: %s" % e)
    try:
        creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    except Exception as e:
        raise AuthError(
            "no Application Default Credentials found; refusing to run (%s). "
            "On Cloud Run the job's runtime service account provides ADC." % e
        )
    if creds is None:
        raise AuthError("no Application Default Credentials found; refusing to run")
    return creds, project


def runtime_project() -> str:
    _, project = _credentials()
    return project or RUNTIME_PROJECT_DEFAULT


def runtime_identity() -> str:
    """The SA email ADC authenticates as (metadata server on Cloud Run).

    Some google-auth metadata credential flavours leave service_account_email unset;
    fall back to resolving the identity from a live token via tokeninfo.
    """
    creds, _ = _credentials()
    email = getattr(creds, "service_account_email", None)
    if email and email != "default":
        return email
    # compute_engine credentials report 'default' until refreshed; resolve via metadata server
    import urllib.request

    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
        headers={"Metadata-Flavor": "Google"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            email = resp.read().decode().strip()
    except Exception as e:
        raise AuthError("could not resolve runtime identity from metadata server: %s" % e)
    if not email or "@" not in email:
        raise AuthError("metadata server returned no usable service account email")
    return email


def expected_writer_sa() -> str:
    """The runtime SA this job must run as (overridable via FINOPS_WRITER_SA)."""
    return os.environ.get("FINOPS_WRITER_SA", "").strip() or WRITER_SA_DEFAULT


def assert_runtime_identity() -> str:
    """Fail closed unless ADC runs as the expected writer/runtime SA."""
    email = runtime_identity()
    want = expected_writer_sa()
    if email != want:
        raise AuthError(
            "finops cloudrun identity check failed: runtime SA is %r, expected %r. "
            "Refusing to pull or write." % (email, want)
        )
    return email


def secret(name: str) -> str:
    """Value of one file-mounted secret by logical name; never printed or logged."""
    filename = SECRET_FILES.get(name)
    if not filename:
        raise AuthError("unknown finops secret name: %r" % name)
    base = secrets_dir()
    candidates = [
        base / filename,  # flat layout: one dir, many files (single-secret volume)
        base / filename / filename,  # per-secret volume: <prefix>/<SECRET_NAME>/<file>
    ]
    for path in candidates:
        if path.is_file():
            value = path.read_text().strip()
            if not value:
                raise AuthError("secret file is empty: %s" % path)
            return value
    raise AuthError(
        "secret file missing for %r (looked in %s); mount FINOPS_SECRETS_DIR=%s with Secret Manager volumes"
        % (name, ", ".join(str(p) for p in candidates), base)
    )


def access_token() -> str:
    """Short-lived ADC access token for REST calls (Firestore etc.)."""
    import google.auth.transport.requests

    creds, _ = _credentials()
    if not creds.valid:
        creds.refresh(google.auth.transport.requests.Request())
    if not creds.token:
        raise AuthError("ADC produced an empty access token")
    return creds.token


class Token:
    """Drop-in for ``gcpauth.Token``: ADC-backed, refreshed on demand."""

    TTL = 30 * 60

    def __init__(self) -> None:
        self._value = ""
        self._at = 0.0

    def get(self, force: bool = False) -> str:
        import time

        if force or not self._value or (time.time() - self._at) > self.TTL:
            self._value = access_token()
            self._at = time.time()
        return self._value


TOKEN = Token()


if __name__ == "__main__":
    import sys

    which = sys.argv[1] if len(sys.argv) > 1 else "identity"
    if which == "identity":
        print(assert_runtime_identity())
    elif which == "secrets":
        # names only; values never printed
        for name in SECRET_FILES:
            secret(name)
            print("secret %s: present" % name)
    else:
        raise SystemExit("usage: cloudrun.py [identity|secrets]")
