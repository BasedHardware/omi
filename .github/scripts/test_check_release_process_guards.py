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
        "shipped release source references unprovisioned beta backend host " "agent-beta.omi.me: app/lib/env.dart"
    ]


def _write_codemagic(tmp_path, workflows: str) -> None:
    (tmp_path / "codemagic.yaml").write_text(f"workflows:\n{workflows}", encoding="utf-8")


def test_codemagic_publisher_guard_rejects_legacy_tag_and_live_release(tmp_path, monkeypatch):
    _write_codemagic(
        tmp_path,
        '''  omi-desktop-swift-release:
    scripts:
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          curl --request POST /v2/desktop/beta/candidates/reserve
          gh release create "$CM_TAG"
  retired-desktop-release:
    scripts:
      - name: Publish
        script: gh release create "$TAG_NAME"
    publishing:
      scripts:
        - isLive: true
''',
    )
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    errors = GUARDS.check_codemagic_release_publishers()

    assert any("legacy $TAG_NAME publisher" in error for error in errors)
    assert any("isLive: true" in error for error in errors)


def test_codemagic_publisher_guard_rejects_duplicate_workflow_key_and_decoy(tmp_path, monkeypatch):
    _write_codemagic(
        tmp_path,
        '''  omi-desktop-swift-release:
    scripts:
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          # gh release create "$CM_TAG"
          echo 'gh release create "$CM_TAG"'
          curl --request POST /v2/desktop/beta/candidates/reserve
  omi-desktop-swift-release:
    scripts: []
''',
    )
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    errors = GUARDS.check_codemagic_release_publishers()

    assert any("duplicate key" in error for error in errors)
    assert any("exact canonical gh release create" in error for error in errors)


def test_codemagic_publisher_guard_requires_reservation_after_smoke_immediately_before_create(tmp_path, monkeypatch):
    _write_codemagic(
        tmp_path,
        '''  omi-desktop-swift-release:
    scripts:
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          curl --request POST /v2/desktop/beta/candidates/reserve
          echo unrelated
          gh release create "$CM_TAG"
''',
    )
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    assert GUARDS.check_codemagic_release_publishers() == [
        "canonical candidate reservation must be immediately before the exact canonical gh release create"
    ]
