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


def test_configure_env_fails_closed_on_gac_file_project_mismatch(monkeypatch, tmp_path):
    # The credential can arrive as a file path (GOOGLE_APPLICATION_CREDENTIALS); the project check must
    # cover it too (cubic review 4939247683).
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    cred = tmp_path / "sa.json"
    cred.write_text(json.dumps({"project_id": "prod-project"}))
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(cred))
    with pytest.raises(SystemExit):
        proof._configure_env(project="dev-project")


def test_configure_env_non_object_service_account_json_is_controlled(monkeypatch):
    # Valid JSON that is NOT an object (a bare list) must not crash with AttributeError.
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", "[1, 2, 3]")
    proof._configure_env(project="any-project")  # no project to compare -> no raise, no crash
