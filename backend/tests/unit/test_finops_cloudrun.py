"""Tests for the Cloud Run finops producer path (FINOPS_AUTH=cloudrun).

Covers the identity boundary (cloudrun.py), the auth-mode switch in the pipeline
modules, the bq_stub translation layer, and the scheduler provisioning contract.
The laptop path (FINOPS_AUTH unset / gcpauth) must be untouched: the existing
test_finops_unit_cost.py suite keeps passing alongside these.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

_FINOPS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "finops"
_BACKEND = pathlib.Path(__file__).resolve().parents[2]


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def cloudrun(monkeypatch):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    return _load("finops_cloudrun", _FINOPS / "cloudrun.py")


# ---------------------------------------------------------------- identity


def test_runtime_identity_fails_closed_without_adc(monkeypatch):
    """No usable ADC (or a non-SA ADC) must exit non-zero, never fall through."""
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    # mask any ambient gcloud ADC so the failure path is deterministic
    import types

    import google

    mod = types.ModuleType("google.auth")

    def _raise(scopes=None):
        import google.auth.exceptions as exc

        raise exc.DefaultCredentialsError("no ADC")

    mod.default = _raise
    monkeypatch.setattr(google, "auth", mod, raising=False)
    monkeypatch.setitem(sys.modules, "google.auth", mod)
    cr = _load("finops_cloudrun_noadc", _FINOPS / "cloudrun.py")
    with pytest.raises(SystemExit, match="no Application Default Credentials"):
        cr.runtime_identity()


def _fake_google_auth(monkeypatch, email: str) -> None:
    import types

    import google

    class FakeCreds:
        service_account_email = email

    mod = types.ModuleType("google.auth")
    mod.default = lambda scopes=None: (FakeCreds(), "based-hardware")
    monkeypatch.setattr(google, "auth", mod, raising=False)
    monkeypatch.setitem(sys.modules, "google.auth", mod)


def test_assert_runtime_identity_refuses_a_different_sa(monkeypatch, cloudrun):
    _fake_google_auth(monkeypatch, "someone-else@based-hardware.iam.gserviceaccount.com")
    with pytest.raises(SystemExit, match="runtime SA is"):
        cloudrun.assert_runtime_identity()


def test_expected_writer_sa_override(monkeypatch, cloudrun):
    monkeypatch.setenv("FINOPS_WRITER_SA", "replacement-sa@based-hardware.iam.gserviceaccount.com")
    assert cloudrun.expected_writer_sa() == "replacement-sa@based-hardware.iam.gserviceaccount.com"


def test_assert_runtime_identity_accepts_expected_sa(monkeypatch, cloudrun):
    _fake_google_auth(monkeypatch, cloudrun.WRITER_SA_DEFAULT)
    assert cloudrun.assert_runtime_identity() == cloudrun.WRITER_SA_DEFAULT


# ---------------------------------------------------------------- secrets


def test_secret_reads_mounted_file_never_home_paths(cloudrun, tmp_path, monkeypatch):
    secdir = tmp_path / "secrets"
    secdir.mkdir()
    (secdir / "STRIPE_API_KEY").write_text("  sk-test-value  \n")
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(secdir))
    assert cloudrun.secret("stripe") == "sk-test-value"


def test_secret_missing_file_is_an_error_naming_the_mount(cloudrun, tmp_path, monkeypatch):
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(tmp_path / "absent"))
    with pytest.raises(SystemExit, match="FINOPS_SECRETS_DIR"):
        cloudrun.secret("stripe")


def test_secret_rejects_unknown_name(cloudrun, tmp_path, monkeypatch):
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(tmp_path))
    with pytest.raises(SystemExit, match="unknown finops secret name"):
        cloudrun.secret("not_a_secret")


def test_secret_files_never_reference_hermes_paths(cloudrun):
    assert all("/" not in str(v) for v in cloudrun.SECRET_FILES.values())
    assert str(cloudrun.secrets_dir()).startswith("/run")


# ---------------------------------------------------------------- auth-mode switch


def test_run_unit_cost_defaults_to_local_auth(monkeypatch):
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    mod = _load("finops_ruc_local", _FINOPS / "run_unit_cost.py")
    assert mod.AUTH_MODE == "local"
    assert mod.gcpauth.__name__ == "gcpauth"


def test_fs_uses_cloudrun_token_module_when_env_set(monkeypatch):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    fs = _load("finops_fs_cloudrun", _FINOPS / "fs.py")
    assert fs.TOKEN is not None
    assert fs.PROJECT == "based-hardware"


def test_load_bigquery_cloudrun_binds_writer_to_runtime_identity(monkeypatch):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    mod = _load("finops_lb_cloudrun", _FINOPS / "load_bigquery.py")
    assert mod.AUTH_MODE == "cloudrun"
    assert callable(mod.assert_writer_identity)


def test_pull_gcp_cloudrun_routes_bq_through_stub(monkeypatch):
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    mod = _load("finops_pg_cloudrun", _FINOPS / "pull_gcp.py")
    assert mod.AUTH_MODE == "cloudrun"
    assert mod.READONLY_ENV is None


# ---------------------------------------------------------------- bq stub


def test_bq_stub_refuses_unknown_command():
    p = subprocess.run(
        [sys.executable, str(_FINOPS / "bq_stub.py"), "extract", "x", "y"],
        capture_output=True,
        text=True,
        input="",
    )
    assert p.returncode != 0
    assert "does not implement" in p.stderr


def test_bq_stub_query_requires_stdin_sql():
    p = subprocess.run(
        [sys.executable, str(_FINOPS / "bq_stub.py"), "query", "--format=json"],
        capture_output=True,
        text=True,
        input="",
    )
    assert p.returncode != 0
    assert "requires SQL" in p.stderr


# ---------------------------------------------------------------- scheduler contract


def test_scheduler_args_carry_expected_schedule_and_target():
    prov = _load("finops_prov_sched", _BACKEND / "scripts" / "provision_finops_unit_cost_scheduler.py")
    args = prov.scheduler_http_args(
        "create",
        project="based-hardware",
        region="us-central1",
        scheduler_job="finops-unit-cost-daily",
        cloud_run_job="finops-unit-cost-job",
        service_account="finops-unit-cost-scheduler@based-hardware.iam.gserviceaccount.com",
    )
    assert "--schedule=30 10 * * *" in args
    assert "--time-zone=America/New_York" in args
    assert (
        "--uri=https://run.googleapis.com/v2/projects/based-hardware/locations/us-central1/jobs/finops-unit-cost-job:run"
        in args
    )
    assert "--http-method=POST" in args


def test_scheduler_args_reject_a_foreign_job_name():
    prov = _load("finops_prov_sched2", _BACKEND / "scripts" / "provision_finops_unit_cost_scheduler.py")
    with pytest.raises(ValueError, match="does not match"):
        prov.scheduler_http_args(
            "create",
            project="based-hardware",
            region="us-central1",
            scheduler_job="some-other-job",
            cloud_run_job="finops-unit-cost-job",
            service_account="finops-unit-cost-scheduler@based-hardware.iam.gserviceaccount.com",
        )


# ---------------------------------------------------------------- overlap lease


def test_cloudrun_entry_exposes_identity_and_help_subcommands():
    p = subprocess.run(
        [sys.executable, str(_FINOPS / "cloudrun_entry.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0
    assert "overlap" in p.stdout


def test_cloudrun_entry_identity_fails_closed_without_adc(monkeypatch):
    """Entry subcommand must exit non-zero whenever the runtime identity cannot be proven."""
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("FINOPS_AUTH", "cloudrun")
    # mask ambient gcloud ADC for a deterministic no-ADC environment
    import os

    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_APPLICATION_CREDENTIALS"}
    env["FINOPS_ADC_MASK_DIR"] = "1"
    # run with a scrubbed CLOUDSDK_CONFIG so ~/.config/gcloud ADC is invisible
    env["CLOUDSDK_CONFIG"] = "/nonexistent-gcloud-config"
    p = subprocess.run(
        [sys.executable, str(_FINOPS / "cloudrun_entry.py"), "identity"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode != 0
    assert "no Application Default Credentials" in p.stderr


# ---------------------------------------------------------------- no secrets in git


def test_no_secret_values_checked_in():
    """The producer sources must reference secret FILE NAMES only, never values."""
    forbidden = [
        "sk-ant-",
        "sk-proj-",
        "STRIPE_API_KEY=sk",
        "xoxb-",
        "pha_",
    ]
    for path in _FINOPS.rglob("*.py"):
        if "vendor" in path.parts:
            continue  # vendored upstream admin scripts contain prefix-validation literals
        text = path.read_text(errors="ignore")
        for needle in forbidden:
            assert needle not in text, "%s contains %r" % (path.name, needle)


def test_secret_supports_per_secret_volume_layout(cloudrun, tmp_path, monkeypatch):
    """Cloud Run mounts each secret as <prefix>/<SECRET_NAME>/<file>; both layouts work."""
    d = tmp_path / "secrets" / "STRIPE_API_KEY"  # dir = Secret Manager resource name
    d.mkdir(parents=True)
    val = "sk-" + "test" + "-value"
    (d / "STRIPE_API_KEY").write_text(val + "\n")
    monkeypatch.setenv("FINOPS_SECRETS_DIR", str(tmp_path / "secrets"))
    assert cloudrun.secret("stripe") == val


def test_gap_fill_includes_the_known_hole_and_caps():
    entry = _load("finops_entry_gap", _FINOPS / "cloudrun_entry.py")
    today = dt.date(2026, 10, 6)
    present = {
        (dt.date(2026, 9, 22) + dt.timedelta(days=i)).isoformat()
        for i in range(14)
        if (dt.date(2026, 9, 22) + dt.timedelta(days=i)).isoformat() != "2026-09-27"
    }
    extras, skipped = entry.gap_fill_dates(today, present)
    assert "2026-09-27" in extras
    assert entry.settlement_frontier(today).isoformat() not in extras
    assert extras == sorted(extras)
    many_missing = set()
    extras, skipped = entry.gap_fill_dates(today, many_missing, cap=3)
    assert len(extras) == 3
    assert skipped
    assert extras[0] < extras[-1]


def test_explicit_date_refuses_unsettled_and_accepts_the_hole():
    entry = _load("finops_entry_date", _FINOPS / "cloudrun_entry.py")
    today = dt.date(2026, 10, 6)
    present = {
        (dt.date(2026, 9, 22) + dt.timedelta(days=i)).isoformat()
        for i in range(12)
        if (dt.date(2026, 9, 22) + dt.timedelta(days=i)).isoformat() != "2026-09-27"
    }
    assert entry.parse_explicit_date("2026-09-27", today) == "2026-09-27"
    with pytest.raises(SystemExit, match="not settled"):
        entry.parse_explicit_date("2026-10-05", today)
    with pytest.raises(SystemExit, match="YYYY-MM-DD"):
        entry.parse_explicit_date("09-27", today)
    assert entry.dates_for_run(today, present, "") == ["2026-09-27", "2026-10-04"]
    assert entry.dates_for_run(today, None, "") == ["2026-10-04"]
    assert entry.dates_for_run(today, set(), "2026-09-27") == ["2026-09-27"]


def test_pull_log_tail_is_what_cloud_logging_will_see(tmp_path, monkeypatch):
    monkeypatch.delenv("FINOPS_AUTH", raising=False)
    mod = _load("finops_ruc_tail", _FINOPS / "run_unit_cost.py")
    log = tmp_path / "pull.log"
    log.write_text("provider pull failed: openai_admin.py\nHTTP 401\n")
    assert "HTTP 401" in mod.pull_log_tail(log)
    assert mod.pull_log_tail(tmp_path / "missing.log") == ""
