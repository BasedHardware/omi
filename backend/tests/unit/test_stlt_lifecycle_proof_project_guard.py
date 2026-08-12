"""The lifecycle proof must fail closed when the service-account credential targets a different
project than --project, so a dev proof can't silently read/write another project's data (cubic review
PR 10887, backend/scripts/stlt_lifecycle_proof.py)."""

import json

import pytest

from scripts import stlt_lifecycle_proof as proof


def test_configure_env_fails_closed_on_project_mismatch(monkeypatch):
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", json.dumps({"project_id": "prod-project"}))
    with pytest.raises(SystemExit):
        proof._configure_env(project="dev-project")


def test_configure_env_ok_when_projects_match(monkeypatch):
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", json.dumps({"project_id": "same-project"}))
    proof._configure_env(project="same-project")  # matching credential -> no raise


def test_configure_env_ok_without_service_account(monkeypatch):
    # On-prem (Mongo / no GCP credential): nothing to reconcile, so the project check is inert.
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    proof._configure_env(project="any-project")
