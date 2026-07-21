from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("check-release-process-guards.py")
SPEC = importlib.util.spec_from_file_location("check_release_process_guards", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GUARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARDS)


def test_beta_backend_guard_ignores_fixtures_but_rejects_shipped_source(tmp_path, monkeypatch):
    shipped = tmp_path / "app/lib/env.dart"
    fixture = tmp_path / "app/test/env_test.dart"
    desktop_fixture = tmp_path / "desktop/macos/Tests/RoutingTests.swift"
    workflows = tmp_path / ".github/workflows"
    for path in (shipped, fixture, desktop_fixture):
        path.parent.mkdir(parents=True, exist_ok=True)
    workflows.mkdir(parents=True)
    (tmp_path / "codemagic.yaml").write_text("", encoding="utf-8")

    fixture.write_text("const retired = 'https://api-beta.omi.me';", encoding="utf-8")
    desktop_fixture.write_text('let retired = "pusher-beta.omi.me"', encoding="utf-8")
    shipped.write_text("const api = 'https://api.omi.me';", encoding="utf-8")
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    assert GUARDS.check_no_unprovisioned_beta_backend_hosts() == []

    shipped.write_text("const api = 'https://agent-beta.omi.me';", encoding="utf-8")
    assert GUARDS.check_no_unprovisioned_beta_backend_hosts() == [
        "shipped release source references unprovisioned beta backend host "
        "agent-beta.omi.me: app/lib/env.dart"
    ]


def _write_promote_workflow(root, body: str) -> None:
    path = root / ".github/workflows/desktop_promote_beta.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_beta_promotion_gate_requires_terminal_status_wait_before_conclusion(tmp_path, monkeypatch):
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    # Race: reads .conclusion of the dispatched qualification_run_id with no wait.
    _write_promote_workflow(
        tmp_path,
        'inputs:\n  qualification_run_id:\n'
        'run: |\n'
        '  run=$(gh api "repos/$REPO/actions/runs/$QUALIFICATION_RUN_ID")\n'
        '  test "$(jq -r .conclusion <<<"$run")" = success\n',
    )
    assert GUARDS.check_desktop_beta_promotion_qualification_gate() == [
        "beta promotion must wait for the qualification run to reach a terminal "
        "status (completed) before checking its conclusion (#10186 race)"
    ]

    # Fixed: polls for status=completed before checking conclusion.
    _write_promote_workflow(
        tmp_path,
        'inputs:\n  qualification_run_id:\n'
        'run: |\n'
        '  for _ in $(seq 1 60); do\n'
        '    run=$(gh api "repos/$REPO/actions/runs/$QUALIFICATION_RUN_ID")\n'
        '    [ "$(jq -r .status <<<"$run")" = completed ] && break\n'
        '    sleep 10\n'
        '  done\n'
        '  test "$(jq -r .status <<<"$run")" = completed || exit 1\n'
        '  test "$(jq -r .conclusion <<<"$run")" = success\n',
    )
    assert GUARDS.check_desktop_beta_promotion_qualification_gate() == []


def test_beta_promotion_gate_is_na_without_a_dispatched_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)
    # A workflow_run-triggered promotion removes the race by construction (no
    # qualification_run_id input) — the gate does not apply.
    _write_promote_workflow(tmp_path, "on:\n  workflow_run:\n    workflows: [desktop_qualify_beta]\n")
    assert GUARDS.check_desktop_beta_promotion_qualification_gate() == []
