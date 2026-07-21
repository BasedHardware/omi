from __future__ import annotations

import importlib.util
import os
import subprocess
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


def _canonical_release_workflow(extra_release_script: str = "", extra_workflows: str = "") -> str:
    extra = (
        f"\n          {extra_release_script.replace(chr(10), chr(10) + '          ')}" if extra_release_script else ""
    )
    return f'''  omi-desktop-swift-release:
    scripts:
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          curl --request POST /v2/desktop/beta/candidates/reserve
          gh release create "$CM_TAG"{extra}
{extra_workflows}'''


def test_codemagic_publisher_guard_rejects_attached_hash_command_substitution_that_bash_executes(tmp_path, monkeypatch):
    """The fixture proves `#` is attached to a word, not a Bash comment boundary."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    counter = tmp_path / "gh-invocations"
    stub = stub_dir / "gh"
    stub.write_text("#!/bin/sh\nprintf '1\\n' >> \"$GH_STUB_COUNTER\"\n", encoding="utf-8")
    stub.chmod(0o755)

    script = 'echo harmless#$(gh release create "$TAG_NAME")'
    completed = subprocess.run(
        ["bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}", "GH_STUB_COUNTER": str(counter)},
    )

    assert completed.returncode == 0, completed.stderr
    assert counter.read_text(encoding="utf-8").splitlines() == ["1"]

    _write_codemagic(tmp_path, _canonical_release_workflow(script))
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    errors = GUARDS.check_codemagic_release_publishers()

    assert any("exactly one release-create authority occurrence" in error for error in errors)


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


def test_codemagic_publisher_guard_scans_executable_shell_command_streams(tmp_path, monkeypatch):
    alternate_publishers = (
        'GH_TOKEN=x gh release create "$TAG_NAME"',
        'command gh release create "$TAG_NAME"',
        'env GH_TOKEN=x gh release create "$TAG_NAME"',
        'if true; then gh release create "$TAG_NAME"; fi',
        'true; gh release create "$TAG_NAME"',
        'gh release \\\n          create "$TAG_NAME"',
    )
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    for alternate_publisher in alternate_publishers:
        indented_publisher = alternate_publisher.replace("\n", "\n          ")
        _write_codemagic(
            tmp_path,
            f'''  omi-desktop-swift-release:
    scripts:
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          curl --request POST /v2/desktop/beta/candidates/reserve
          gh release create "$CM_TAG"
  alternate:
    scripts:
      - name: Publish
        script: |
          {indented_publisher}
''',
        )

        errors = GUARDS.check_codemagic_release_publishers()

        assert any("legacy $TAG_NAME publisher" in error for error in errors), alternate_publisher


def test_codemagic_publisher_guard_rejects_extra_create_and_reservation_decoys(tmp_path, monkeypatch):
    _write_codemagic(
        tmp_path,
        '''  omi-desktop-swift-release:
    scripts:
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          echo /v2/desktop/beta/candidates/reserve
          gh release create "$CM_TAG"
          true; gh release create "$CM_TAG"
''',
    )
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    errors = GUARDS.check_codemagic_release_publishers()

    assert any("exactly one executable" in error for error in errors)
    assert any("exact canonical gh release create" in error for error in errors)
    assert any("canonical candidate reservation" in error for error in errors)


def test_codemagic_publisher_guard_rejects_comments_and_quoted_decoys(tmp_path, monkeypatch):
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    for decoy in (
        '# gh release create "$TAG_NAME"',
        "echo 'gh release create \"$TAG_NAME\"'",
        "printf '%s\\n' 'gh release create \"$TAG_NAME\"'",
    ):
        _write_codemagic(tmp_path, _canonical_release_workflow(decoy))

        errors = GUARDS.check_codemagic_release_publishers()

        assert any("exactly one release-create authority occurrence" in error for error in errors), decoy


def test_codemagic_publisher_guard_rejects_indirect_and_path_authority(tmp_path, monkeypatch):
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    for alternate_publisher in (
        'PUBLISH=\'gh release create "$TAG_NAME"\'\neval "$PUBLISH"',
        'GH=gh\n$GH release create "$TAG_NAME"',
        '/usr/local/bin/gh release create "$TAG_NAME"',
        'echo harmless\\ #$(gh release create "$TAG_NAME")',
    ):
        _write_codemagic(tmp_path, _canonical_release_workflow(alternate_publisher))

        errors = GUARDS.check_codemagic_release_publishers()

        assert any("release-create authority" in error for error in errors), alternate_publisher


def test_codemagic_publisher_guard_fails_closed_on_malformed_shell_near_authority(tmp_path, monkeypatch):
    _write_codemagic(tmp_path, _canonical_release_workflow("echo 'unterminated\ngh release create \"$TAG_NAME\""))
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    errors = GUARDS.check_codemagic_release_publishers()

    assert any("malformed shell syntax around release-create authority" in error for error in errors)


def test_codemagic_publisher_guard_accepts_only_the_canonical_authority(tmp_path, monkeypatch):
    _write_codemagic(tmp_path, _canonical_release_workflow())
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    assert GUARDS.check_codemagic_release_publishers() == []


def test_codemagic_publisher_guard_rejects_dynamic_release_create(tmp_path, monkeypatch):
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
  alternate:
    scripts:
      - name: Publish
        script: |
          eval 'gh release create "$TAG_NAME"'
          bash -c 'gh release create "$TAG_NAME"'
          echo $(gh release create "$TAG_NAME")
''',
    )
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)

    assert any("cannot safely interpret" in error for error in GUARDS.check_codemagic_release_publishers())
