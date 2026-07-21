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
