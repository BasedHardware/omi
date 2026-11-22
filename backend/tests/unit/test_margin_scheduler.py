"""Margin scheduling cannot enable shadow mode or redirect to another job."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "margin_scheduler", Path(__file__).resolve().parents[2] / "scripts/provision_margin_scheduler.py"
)
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


def active_job():
    return {
        "spec": {
            "template": {
                "spec": {
                    "template": {
                        "spec": {
                            "serviceAccountName": scheduler.RUNTIME_SA,
                            "containers": [
                                {
                                    "image": "us-central1-docker.pkg.dev/based-hardware/omi-margin/producer:"
                                    + "a" * 40,
                                    "args": [
                                        "run",
                                        "--mode",
                                        "active",
                                        "--inputs",
                                        "margin/inputs/" + "b" * 64 + ".json",
                                    ],
                                }
                            ],
                        }
                    }
                }
            }
        }
    }


def schedule_state():
    return {
        "schedule": "12 * * * *",
        "timeZone": "UTC",
        "state": "ENABLED",
        "httpTarget": {
            "uri": scheduler.URI,
            "httpMethod": "POST",
            "oauthToken": {
                "serviceAccountEmail": scheduler.SCHEDULER_SA,
                "scope": "https://www.googleapis.com/auth/cloud-platform",
            },
        },
    }


def test_shadow_or_foreign_runtime_cannot_enable_schedule(monkeypatch):
    for field, value in (
        ("mode", "shadow"),
        ("image", "gcr.io/other/producer:latest"),
        ("identity", "other@example.test"),
    ):
        job = active_job()
        task = job["spec"]["template"]["spec"]["template"]["spec"]
        if field == "mode":
            task["containers"][0]["args"][2] = value
        elif field == "image":
            task["containers"][0]["image"] = value
        else:
            task["serviceAccountName"] = value
        calls = []

        def command(*args):
            calls.append(args)
            return SimpleNamespace(returncode=0, stdout=json.dumps(job))

        monkeypatch.setattr(scheduler, "command", command)
        with pytest.raises(ValueError, match="active producer"):
            scheduler.main()
        assert len(calls) == 1  # Refuse before any scheduler mutation.


def test_create_targets_only_margin_and_verifies_identity(monkeypatch):
    responses = [
        SimpleNamespace(returncode=0, stdout=json.dumps(active_job())),
        SimpleNamespace(returncode=1, stderr="NOT_FOUND"),
        SimpleNamespace(returncode=0),
        SimpleNamespace(returncode=0, stdout=json.dumps(schedule_state())),
    ]
    calls = []

    def command(*args):
        calls.append(args)
        return responses.pop(0)

    monkeypatch.setattr(scheduler, "command", command)
    scheduler.main()
    mutation = calls[2]
    assert mutation[:5] == ("scheduler", "jobs", "create", "http", "omi-margin-hourly")
    assert "--uri=" + scheduler.URI in mutation
    assert "--max-retry-attempts=0" in mutation
    assert "--schedule=12 * * * *" in mutation
    assert "finops-unit-cost-daily" not in mutation
    for key, value in (("state", "PAUSED"), ("timeZone", "America/New_York")):
        changed = copy.deepcopy(schedule_state())
        changed[key] = value
        with pytest.raises(ValueError, match="readback"):
            scheduler.verify_schedule(changed)


def test_permission_failure_is_not_misclassified_as_missing_scheduler(monkeypatch):
    calls = []

    def command(*args):
        calls.append(args)
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout=json.dumps(active_job()))
        return SimpleNamespace(returncode=1, stderr="PERMISSION_DENIED")

    monkeypatch.setattr(scheduler, "command", command)
    with pytest.raises(SystemExit, match="inspection failed"):
        scheduler.main()
    assert len(calls) == 2
