"""Private backend-listen env: Secret Manager migration and the pre-roll guard never leak a value."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github" / "scripts" / "listen_private_env.py"
PROD_VALUES = ROOT / "backend" / "charts" / "backend-listen" / "prod_omi_backend_listen_values.yaml"
SPEC = importlib.util.spec_from_file_location("listen_private_env", SCRIPT)
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)

COHORT = "uid:SentinelCohort0123456789"
DIGEST = "f" * 64
SECRET_NAME = "prod-omi-backend-listen-private-env"


class Cluster:
    """Fake kubectl/gcloud: records argv, serves JSON, never prints."""

    def __init__(self, live: dict[str, dict], secret: dict[str, str] | None, ready: bool = True):
        self.live = live
        self.secret = secret
        self.ready = ready
        self.version = "1-aaaa"
        self.calls: list[list[str]] = []
        self.written: dict | None = None
        self.replicasets: list[tuple[int, dict]] = [(35, live)]
        self.secret_written = "2026-11-18T00:00:00Z"
        self.pod_starts = ["2026-11-18T01:00:00Z", "2026-11-18T02:00:00Z"]
        self.include_data_fields = True
        self.allow_replicaset_read = True

    def __call__(self, argv, *, timeout=60):
        self.calls.append(list(argv))
        if argv[:4] == ["gcloud", "secrets", "versions", "add"]:
            path = next(a.split("=", 1)[1] for a in argv if a.startswith("--data-file="))
            self.written = json.loads(Path(path).read_text())
            assert Path(path).stat().st_mode & 0o777 == 0o600
            return b"projects/1/secrets/LISTEN_PRIVATE_ENV/versions/3\n"
        if "annotate" in argv:
            self.version = "1-bbbb"
            return b""
        kind = argv[argv.index("get") + 1]
        if kind == "deployment":
            env = [dict(entry, name=name) for name, entry in self.live.items()]
            return json.dumps(
                {
                    "spec": {
                        "selector": {"matchLabels": {"app": "listen"}},
                        "template": {"spec": {"containers": [{"name": "backend-listen", "env": env}]}},
                    }
                }
            ).encode()
        if kind == "replicaset":
            if not self.allow_replicaset_read:
                raise HELPER.Refused("kubectl get failed (exit 1)")
            assert argv[argv.index("-l") + 1] == "app=listen"
            items = []
            for replicas, live in self.replicasets:
                env = [dict(entry, name=name) for name, entry in live.items()]
                items.append(
                    {
                        "metadata": {"ownerReferences": [{"name": "prod-omi-backend-listen"}]},
                        "status": {"replicas": replicas},
                        "spec": {"template": {"spec": {"containers": [{"name": "backend-listen", "env": env}]}}},
                    }
                )
            return json.dumps({"items": items}).encode()
        if kind == "pod":
            assert argv[argv.index("-l") + 1] == "app=listen"
            items = [{"status": {"phase": "Running", "startTime": t}} for t in self.pod_starts]
            return json.dumps({"items": items}).encode()
        if kind == "secret":
            if self.secret is None:
                raise HELPER.Refused("kubectl get failed (exit 1)")
            metadata = {"name": SECRET_NAME, "creationTimestamp": "2026-11-17T00:00:00Z"}
            if "--show-managed-fields=true" in argv:
                fields = {"f:type": {}}
                if self.include_data_fields:
                    fields["f:data"] = {".": {}, **{f"f:{key}": {} for key in self.secret}}
                metadata["managedFields"] = [
                    {
                        "manager": "external-secrets",
                        "operation": "Update",
                        "apiVersion": "v1",
                        "time": self.secret_written,
                        "fieldsType": "FieldsV1",
                        "fieldsV1": fields,
                    }
                ]
            return json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": metadata,
                    "data": {k: base64.b64encode(v.encode()).decode() for k, v in self.secret.items()},
                }
            ).encode()
        if kind == "externalsecret":
            return json.dumps(
                {
                    "status": {
                        "syncedResourceVersion": self.version,
                        "refreshTime": "t",
                        "conditions": [{"type": "Ready", "status": str(self.ready)}],
                    }
                }
            ).encode()
        raise AssertionError(argv)


@pytest.fixture
def cluster(monkeypatch):
    def install(**kwargs):
        fake = Cluster(**kwargs)
        monkeypatch.setattr(HELPER, "run", fake)
        monkeypatch.setattr(HELPER.time, "sleep", lambda _s: None)
        return fake

    return install


def literal_live():
    return {
        "STT_CAP_DISPATCH_COHORT": {"value": COHORT},
        "MEDIA_NOISE_MODE_SERVE_UID_SHA256S": {"value": DIGEST},
        "STT_CAP_DISPATCH_ENFORCEMENT": {"value": "true"},
    }


def full_secret(**changes):
    secret = {
        "STT_CAP_DISPATCH_ENFORCEMENT": "true",
        "STT_CAP_DISPATCH_COHORT": COHORT,
        "MEDIA_NOISE_MODE_SERVE_UID_SHA256S": DIGEST,
    }
    secret.update(changes)
    return secret


def ref(key):
    return {"valueFrom": {"secretKeyRef": {"name": SECRET_NAME, "key": key, "optional": False}}}


def guard(capsys, timeout="5"):
    rc = HELPER.main(["guard", "--values-file", str(PROD_VALUES), "--timeout", timeout])
    out = capsys.readouterr()
    assert COHORT not in out.out + out.err and DIGEST not in out.out + out.err
    return rc, out.out, out.err


def test_prod_chart_declares_the_private_names():
    values = yaml.safe_load(PROD_VALUES.read_text())
    assert HELPER.declared(values) == (
        SECRET_NAME,
        ["STT_CAP_DISPATCH_ENFORCEMENT", "STT_CAP_DISPATCH_COHORT", "MEDIA_NOISE_MODE_SERVE_UID_SHA256S"],
    )


def test_guard_passes_when_secret_matches_live_literals(cluster, capsys):
    cluster(live=literal_live(), secret=full_secret())
    rc, out, _ = guard(capsys)
    assert rc == 0
    assert "key=STT_CAP_DISPATCH_COHORT effect=same" in out
    assert "key=MEDIA_NOISE_MODE_SERVE_UID_SHA256S effect=same" in out


def test_guard_refuses_a_changed_or_missing_value_before_any_roll(cluster, capsys):
    cluster(live=literal_live(), secret={"STT_CAP_DISPATCH_COHORT": COHORT + "x"})
    rc, out, err = guard(capsys)
    assert rc == 2
    assert "key=STT_CAP_DISPATCH_COHORT effect=changed" in out
    assert "key=MEDIA_NOISE_MODE_SERVE_UID_SHA256S effect=missing-from-secret" in out
    assert "nothing deployed" in err


def test_guard_after_cutover_checks_references_and_presence(cluster, capsys):
    live = {key: ref(key) for key in full_secret()}
    cluster(live=live, secret=full_secret())
    assert guard(capsys)[0] == 0
    # An emptied key would deny every capped dispatch (empty cohort with enforcement on).
    cluster(live=live, secret=full_secret(STT_CAP_DISPATCH_COHORT=""))
    rc, out, _ = guard(capsys)
    assert rc == 2 and "key=STT_CAP_DISPATCH_COHORT effect=missing-from-secret" in out


def test_guard_after_cutover_refuses_a_secret_change_no_pod_serves_yet(cluster, capsys):
    # A value change synced after the pods started would ride the next roll unannounced.
    live = {key: ref(key) for key in full_secret()}
    fake = cluster(live=live, secret=full_secret(STT_CAP_DISPATCH_COHORT=COHORT + ",uid:other"))
    fake.secret_written = "2026-11-18T01:30:00Z"
    rc, out, err = guard(capsys)
    assert rc == 2
    assert "key=STT_CAP_DISPATCH_COHORT effect=pending-restart" in out
    assert "nothing deployed" in err
    # After the runbook's rollout restart every serving pod is newer than the Secret.
    fake.pod_starts = ["2026-11-18T01:40:00Z"]
    assert guard(capsys)[0] == 0


def test_guard_after_cutover_refuses_metadata_only_update_evidence(cluster, capsys):
    live = {key: ref(key) for key in full_secret()}
    fake = cluster(live=live, secret=full_secret())
    fake.include_data_fields = False
    rc, _, err = guard(capsys)
    assert rc == 2 and "no reliable data update timestamp" in err


def test_guard_refuses_an_unsynced_external_secret(cluster, capsys):
    cluster(live=literal_live(), secret=None, ready=False)
    rc, _, err = guard(capsys, timeout="0")
    assert rc == 2 and "not Ready" in err


def test_guard_is_a_no_op_without_declared_names(tmp_path, cluster, capsys):
    values = tmp_path / "values.yaml"
    values.write_text("env: []\n")
    fake = cluster(live={}, secret=None)
    assert HELPER.main(["guard", "--values-file", str(values)]) == 0
    assert fake.calls == []


def private_yaml(**env):
    return yaml.safe_dump({"privateEnv": env})


def migrate(capsys, monkeypatch, secret_yaml):
    monkeypatch.setenv("LISTEN_PRIVATE_VALUES_YAML", secret_yaml)
    rc = HELPER.main(["migrate", "--values-file", str(PROD_VALUES), "--project", "synthetic-project"])
    out = capsys.readouterr()
    assert COHORT not in out.out + out.err and DIGEST not in out.out + out.err
    import os

    assert "LISTEN_PRIVATE_VALUES_YAML" not in os.environ
    return rc, out.out, out.err


def full_overlay(**changes):
    env = {
        "MEDIA_NOISE_MODE": "off",
        "MEDIA_NOISE_MODE_SERVE_PERCENT": "0",
        "MEDIA_NOISE_MODE_SERVE_UID_SHA256S": DIGEST,
        "STT_CAP_DISPATCH_COHORT": COHORT,
        "STT_CAP_DISPATCH_ENFORCEMENT": "true",
        "STT_CAP_DISPATCH_LANES": "live",
    }
    env.update(changes)
    return private_yaml(**env)


def test_migrate_writes_only_the_declared_private_names(cluster, capsys, monkeypatch):
    fake = cluster(live=literal_live(), secret=None)
    rc, out, _ = migrate(capsys, monkeypatch, full_overlay())
    assert rc == 0, out
    assert fake.written == {
        "STT_CAP_DISPATCH_ENFORCEMENT": "true",
        "STT_CAP_DISPATCH_COHORT": COHORT,
        "MEDIA_NOISE_MODE_SERVE_UID_SHA256S": DIGEST,
    }
    assert "new Secret Manager version added" in out
    for key in (
        "MEDIA_NOISE_MODE",
        "MEDIA_NOISE_MODE_SERVE_PERCENT",
        "STT_CAP_DISPATCH_LANES",
    ):
        assert f"key={key} effect=public-same" in out
    assert "key=STT_CAP_DISPATCH_COHORT effect=source-same" in out


@pytest.mark.parametrize(
    ("overlay", "effect"),
    [
        (full_overlay(STT_CAP_DISPATCH_LANES="live,sync"), "key=STT_CAP_DISPATCH_LANES effect=public-changed"),
        (full_overlay(EDGE_SHADOW_TOKEN="x" * 30), "key=EDGE_SHADOW_TOKEN effect=undeclared"),
        (full_overlay(STT_CAP_DISPATCH_COHORT=""), "key=STT_CAP_DISPATCH_COHORT effect=missing-from-source"),
        (
            private_yaml(STT_CAP_DISPATCH_COHORT=COHORT),
            "key=MEDIA_NOISE_MODE_SERVE_UID_SHA256S effect=missing-from-source",
        ),
    ],
)
def test_migrate_refuses_a_mismatched_source_and_writes_nothing(cluster, capsys, monkeypatch, overlay, effect):
    fake = cluster(live=literal_live(), secret=None)
    rc, out, err = migrate(capsys, monkeypatch, overlay)
    assert rc == 2
    assert effect in out
    assert "nothing written" in err
    assert fake.written is None


@pytest.mark.parametrize("live_template", ["deployment", "replicaset"])
def test_migrate_refuses_a_serving_literal_mismatch_before_writing(cluster, capsys, monkeypatch, live_template):
    fake = cluster(live=literal_live(), secret=None)
    mismatched = dict(literal_live(), STT_CAP_DISPATCH_COHORT={"value": COHORT + "x"})
    if live_template == "deployment":
        fake.live = mismatched
    else:
        fake.replicasets.append((3, mismatched))
    rc, out, err = migrate(capsys, monkeypatch, full_overlay())
    assert rc == 2 and "nothing written" in err
    assert "key=STT_CAP_DISPATCH_COHORT effect=source-changed" in out
    assert fake.written is None


def test_migrate_refuses_when_serving_state_cannot_be_read(cluster, capsys, monkeypatch):
    fake = cluster(live=literal_live(), secret=None)
    fake.allow_replicaset_read = False
    assert migrate(capsys, monkeypatch, full_overlay())[0] == 2
    assert fake.written is None


def test_migrate_refuses_when_serving_values_are_already_references(cluster, capsys, monkeypatch):
    fake = cluster(live={key: ref(key) for key in full_secret()}, secret=full_secret())
    rc, out, err = migrate(capsys, monkeypatch, full_overlay())
    assert rc == 2 and "nothing written" in err
    assert "key=STT_CAP_DISPATCH_COHORT effect=source-no-serving-literal" in out
    assert fake.written is None


def test_migrate_refuses_bad_yaml_without_echoing_it(cluster, capsys, monkeypatch):
    fake = cluster(live=literal_live(), secret=None)
    rc, out, err = migrate(capsys, monkeypatch, f'privateEnv:\n  STT_CAP_DISPATCH_COHORT: "{COHORT}\n')
    assert rc == 2 and fake.written is None


def test_sync_waits_for_a_fresh_sync_after_force_sync(cluster, capsys):
    fake = cluster(live={}, secret=None)
    assert HELPER.main(["sync", "--values-file", str(PROD_VALUES), "--timeout", "5"]) == 0
    assert any("annotate" in call for call in fake.calls)
    assert "ready" in capsys.readouterr().out


def test_guard_checks_every_serving_replicaset_not_only_the_template(cluster, capsys):
    secret = full_secret()
    fake = cluster(live=literal_live(), secret=secret)
    older = dict(literal_live(), STT_CAP_DISPATCH_COHORT={"value": "uid:older"})
    fake.replicasets = [
        (35, literal_live()),
        (3, older),
        (0, {"STT_CAP_DISPATCH_COHORT": {"value": "uid:scaled-down"}}),
    ]
    rc, out, _ = guard(capsys)
    assert rc == 2
    assert "key=STT_CAP_DISPATCH_COHORT effect=changed+same" in out
    assert "key=MEDIA_NOISE_MODE_SERVE_UID_SHA256S effect=same" in out
