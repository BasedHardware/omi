"""Regression coverage for the cross-resource shared-config migration guard.

These fixtures model the historical partial transition that caused the
2026-07-22 Pusher outage: a shared key (REDIS_DB_HOST) removed/reclassified
from a source while a serving workload still referenced the old source/key.
"""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "backend" / "scripts" / "verify_shared_config_migration.py"


@pytest.fixture(scope="module")
def guard() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def _write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


# A Deployment that still binds REDIS_DB_HOST to the historical Secret source
# AFTER the key moved to the ConfigMap — the exact incident shape.
STALE_SECRET_RENDER = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dev-omi-pusher
spec:
  template:
    spec:
      containers:
        - name: pusher
          env:
            - name: REDIS_DB_HOST
              valueFrom:
                secretKeyRef:
                  name: dev-omi-backend-secrets
                  key: REDIS_DB_HOST
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: dev-omi-backend-secrets
                  key: OPENAI_API_KEY
"""

# A Deployment whose REDIS_DB_HOST binding already moved to the ConfigMap — the
# compatible consumer rollout that must precede the source transition.
CLEAN_CONFIGMAP_RENDER = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dev-omi-pusher
spec:
  template:
    spec:
      containers:
        - name: pusher
          env:
            - name: REDIS_DB_HOST
              valueFrom:
                configMapKeyRef:
                  name: dev-omi-backend-config
                  key: REDIS_DB_HOST
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: dev-omi-backend-secrets
                  key: OPENAI_API_KEY
"""

# Proposed state: REDIS_DB_HOST now lives ONLY in the ConfigMap; the Secret no
# longer carries it. Key names only — no values ever appear.
PROPOSED_INVENTORY = """\
configmaps:
  dev-omi-backend-config:
    - REDIS_DB_HOST
    - GOOGLE_CLIENT_ID
secrets:
  dev-omi-backend-secrets:
    - OPENAI_API_KEY
    - REDIS_DB_PASSWORD
"""

# Current live state: REDIS_DB_HOST still materializes in the Secret (pre-move).
PREVIOUS_INVENTORY = """\
configmaps:
  dev-omi-backend-config:
    - GOOGLE_CLIENT_ID
secrets:
  dev-omi-backend-secrets:
    - REDIS_DB_HOST
    - OPENAI_API_KEY
    - REDIS_DB_PASSWORD
"""


def test_blocks_the_historical_partial_transition(guard, tmp_path, capsys):
    """A workload still referencing the removed Secret key must fail closed."""
    rendered = _write(tmp_path / "rendered.yaml", STALE_SECRET_RENDER)
    inventory = _write(tmp_path / "proposed.yaml", PROPOSED_INVENTORY)
    previous = _write(tmp_path / "previous.yaml", PREVIOUS_INVENTORY)

    rc = guard.main(
        ["guard", "--rendered", rendered, "--source-inventory", inventory, "--previous-inventory", previous]
    )
    out = capsys.readouterr().out
    assert rc == 1
    assert "REDIS_DB_HOST" in out
    assert "not present in the proposed source inventory" in out
    # The guard must name the reclassification so an operator sees the fix path.
    assert "moved to configmap/dev-omi-backend-config" in out


def test_passes_when_consumer_rolled_first(guard, tmp_path, capsys):
    """The compatible consumer rollout (ConfigMap binding) passes the transition."""
    rendered = _write(tmp_path / "rendered.yaml", CLEAN_CONFIGMAP_RENDER)
    inventory = _write(tmp_path / "proposed.yaml", PROPOSED_INVENTORY)
    previous = _write(tmp_path / "previous.yaml", PREVIOUS_INVENTORY)

    rc = guard.main(
        ["guard", "--rendered", rendered, "--source-inventory", inventory, "--previous-inventory", previous]
    )
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "passed" in out


def test_blocks_a_missing_key_without_transition(guard, tmp_path, capsys):
    """Even without a previous inventory, a reference to an absent key fails."""
    rendered = _write(tmp_path / "rendered.yaml", STALE_SECRET_RENDER)
    inventory = _write(tmp_path / "proposed.yaml", PROPOSED_INVENTORY)

    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    out = capsys.readouterr().out
    assert rc == 1
    assert "REDIS_DB_HOST" in out


def test_blocks_a_reference_to_a_removed_object(guard, tmp_path, capsys):
    """A reference to an object absent from the proposed inventory fails."""
    rendered = _write(tmp_path / "rendered.yaml", CLEAN_CONFIGMAP_RENDER)
    # Inventory drops the ConfigMap object entirely.
    inventory = _write(
        tmp_path / "proposed.yaml",
        "secrets:\n  dev-omi-backend-secrets:\n    - OPENAI_API_KEY\n",
    )
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    out = capsys.readouterr().out
    assert rc == 1
    assert "configmap/dev-omi-backend-config" in out
    assert "absent from the proposed source inventory" in out


def test_fails_closed_on_missing_inventory_file(guard, tmp_path, capsys):
    rendered = _write(tmp_path / "rendered.yaml", CLEAN_CONFIGMAP_RENDER)
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", str(tmp_path / "nope.yaml")])
    assert rc == 1
    assert "could not read inventory" in capsys.readouterr().out


def test_fails_closed_on_malformed_inventory(guard, tmp_path, capsys):
    rendered = _write(tmp_path / "rendered.yaml", CLEAN_CONFIGMAP_RENDER)
    inventory = _write(tmp_path / "proposed.yaml", "configmaps: not-a-mapping\n")
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    assert rc == 1
    assert "must be a mapping" in capsys.readouterr().out


def test_fails_closed_on_empty_inventory(guard, tmp_path, capsys):
    rendered = _write(tmp_path / "rendered.yaml", CLEAN_CONFIGMAP_RENDER)
    inventory = _write(tmp_path / "proposed.yaml", "configmaps: {}\nsecrets: {}\n")
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    assert rc == 1
    assert "declares no configmaps or secrets" in capsys.readouterr().out


def test_rejects_a_malformed_binding(guard, tmp_path, capsys):
    rendered = _write(
        tmp_path / "rendered.yaml",
        """\
apiVersion: apps/v1
kind: Deployment
metadata: {name: bad}
spec:
  template:
    spec:
      containers:
        - name: pusher
          env:
            - name: REDIS_DB_HOST
              valueFrom:
                secretKeyRef:
                  name: dev-omi-backend-secrets
""",
    )
    inventory = _write(tmp_path / "proposed.yaml", "secrets:\n  dev-omi-backend-secrets:\n    - REDIS_DB_HOST\n")
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    assert rc == 1
    assert "must declare a non-empty name and key" in capsys.readouterr().out


def test_never_prints_secret_values(guard, tmp_path, capsys):
    """A real-looking literal value must never reach the guard's output."""
    rendered = _write(
        tmp_path / "rendered.yaml",
        """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dev-omi-pusher
spec:
  template:
    spec:
      containers:
        - name: pusher
          env:
            - name: REDIS_DB_HOST
              valueFrom:
                configMapKeyRef:
                  name: dev-omi-backend-config
                  key: REDIS_DB_HOST
            - name: DANGEROUS_LITERAL
              value: super-secret-leak-that-must-never-appear
""",
    )
    inventory = _write(tmp_path / "proposed.yaml", PROPOSED_INVENTORY)
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "super-secret-leak-that-must-never-appear" not in out


# ---------------------------------------------------------------------------
# envFrom bulk-load blind spot (the agreed review finding) + workload generality
# ---------------------------------------------------------------------------

# A Deployment that consumes the shared ConfigMap ONLY via envFrom (no explicit
# per-key ref) — the binding style the original guard missed.
ENVFROM_ONLY_RENDER = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dev-omi-pusher
spec:
  template:
    spec:
      initContainers:
        - name: migrate
          envFrom:
            - configMapRef:
                name: dev-omi-backend-config
      containers:
        - name: pusher
          envFrom:
            - configMapRef:
                name: dev-omi-backend-config
"""


def test_envfrom_object_removal_is_caught(guard, tmp_path, capsys):
    """A bulk-loaded ConfigMap removed from the proposed inventory must fail."""
    rendered = _write(tmp_path / "rendered.yaml", ENVFROM_ONLY_RENDER)
    inventory = _write(
        tmp_path / "proposed.yaml",
        "secrets:\n  dev-omi-backend-secrets:\n    - OPENAI_API_KEY\n",
    )
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    out = capsys.readouterr().out
    assert rc == 1
    assert "envFrom bulk-loads configmap/dev-omi-backend-config" in out
    assert "absent from the proposed source inventory" in out


def test_envfrom_key_removal_is_caught_with_previous_inventory(guard, tmp_path, capsys):
    """A key removed from a bulk-loaded object is the outage class — must fail."""
    rendered = _write(tmp_path / "rendered.yaml", ENVFROM_ONLY_RENDER)
    proposed = _write(
        tmp_path / "proposed.yaml",
        "configmaps:\n  dev-omi-backend-config:\n    - REDIS_DB_HOST\n",
    )
    previous = _write(
        tmp_path / "previous.yaml",
        "configmaps:\n  dev-omi-backend-config:\n    - REDIS_DB_HOST\n    - RETIRED_KEY\n",
    )
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", proposed, "--previous-inventory", previous])
    out = capsys.readouterr().out
    assert rc == 1
    assert "envFrom bulk-loads configmap/dev-omi-backend-config" in out
    assert "RETIRED_KEY" in out
    assert "2026-07-22 outage class" in out


def test_envfrom_passes_when_no_key_removed(guard, tmp_path, capsys):
    """A bulk-loaded object whose keys are unchanged (or only added) passes."""
    rendered = _write(tmp_path / "rendered.yaml", ENVFROM_ONLY_RENDER)
    proposed = _write(
        tmp_path / "proposed.yaml",
        "configmaps:\n  dev-omi-backend-config:\n    - REDIS_DB_HOST\n    - NEW_KEY\n",
    )
    previous = _write(
        tmp_path / "previous.yaml",
        "configmaps:\n  dev-omi-backend-config:\n    - REDIS_DB_HOST\n",
    )
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", proposed, "--previous-inventory", previous])
    assert rc == 0, capsys.readouterr().out


def test_statefulset_and_initcontainers_are_scanned(guard, tmp_path, capsys):
    """A StatefulSet and an initContainer referencing a removed key both fail."""
    rendered = _write(
        tmp_path / "rendered.yaml",
        """\
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: dev-cache
spec:
  template:
    spec:
      initContainers:
        - name: bootstrap
          env:
            - name: REDIS_DB_HOST
              valueFrom:
                secretKeyRef:
                  name: dev-omi-backend-secrets
                  key: REDIS_DB_HOST
      containers:
        - name: cache
""",
    )
    inventory = _write(tmp_path / "proposed.yaml", PROPOSED_INVENTORY)
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    out = capsys.readouterr().out
    assert rc == 1
    assert "REDIS_DB_HOST" in out
    assert "not present in the proposed source inventory" in out


# ---------------------------------------------------------------------------
# Preflight mode (self-contained chart-values scan, no external inventory)
# ---------------------------------------------------------------------------


def test_preflight_passes_on_real_chart_values(guard, capsys):
    """Preflight mode against the committed pusher chart values must pass."""
    rc = guard.main(["preflight"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "shared-config migration preflight passed" in out
    # Both environments are scanned
    assert "dev:" in out
    assert "prod:" in out


def test_preflight_is_the_default_mode(guard, capsys):
    """Running with no mode argument defaults to preflight."""
    rc = guard.main([])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "shared-config migration preflight passed" in out


def test_preflight_detects_malformed_env_binding(guard, tmp_path, capsys):
    """Preflight fails when chart env has an ambiguous dual-source binding."""
    chart_dir = tmp_path / "backend" / "charts" / "pusher"
    chart_dir.mkdir(parents=True)
    for env in ("dev", "prod"):
        (chart_dir / f"{env}_omi_pusher_values.yaml").write_text(
            "env:\n"
            "  - name: BAD_KEY\n"
            "    valueFrom:\n"
            "      configMapKeyRef:\n"
            "        name: cm\n"
            "        key: BAD_KEY\n"
            "      secretKeyRef:\n"
            "        name: sec\n"
            "        key: BAD_KEY\n",
            encoding="utf-8",
        )
    rc = guard.main(["preflight", "--root", str(tmp_path)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "multiple binding sources" in err


def test_guard_mode_requires_rendered_and_inventory(guard, capsys):
    """Guard mode without --rendered or --source-inventory exits with usage error."""
    with pytest.raises(SystemExit) as exc_info:
        guard.main(["guard"])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "requires --rendered" in err


def test_guard_mode_still_works_with_explicit_mode_arg(guard, tmp_path, capsys):
    """Guard mode still works when explicitly invoked with --rendered + --source-inventory."""
    rendered = _write(tmp_path / "rendered.yaml", STALE_SECRET_RENDER)
    inventory = _write(tmp_path / "proposed.yaml", PROPOSED_INVENTORY)
    rc = guard.main(["guard", "--rendered", rendered, "--source-inventory", inventory])
    out = capsys.readouterr().out
    assert rc == 1
    assert "REDIS_DB_HOST" in out
