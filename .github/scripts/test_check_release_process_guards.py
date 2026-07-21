from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("check-release-process-guards.py")
REPO_ROOT = SCRIPT.parents[2]
SPEC = importlib.util.spec_from_file_location("check_release_process_guards", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GUARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARDS)


def _copy_contract_tree(tmp_path: Path, monkeypatch) -> Path:
    shutil.copy2(REPO_ROOT / "codemagic.yaml", tmp_path / "codemagic.yaml")
    fixture = tmp_path / ".github/scripts/fixtures/codemagic_workflow_contract/v1.json"
    fixture.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / ".github/scripts/fixtures/codemagic_workflow_contract/v1.json", fixture)
    monkeypatch.setattr(GUARDS, "ROOT", tmp_path)
    return tmp_path / "codemagic.yaml"


def _mutate(path: Path, old: str, new: str, *, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= count, old
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def _errors_after(tmp_path: Path, monkeypatch, old: str, new: str, *, count: int = 1) -> list[str]:
    codemagic = _copy_contract_tree(tmp_path, monkeypatch)
    _mutate(codemagic, old, new, count=count)
    return GUARDS.check_codemagic_release_publishers()


def _assert_contract_rejects(errors: list[str]) -> None:
    assert any("contract" in error or "fixture" in error for error in errors), errors


def _load_parent_guard(tmp_path: Path):
    """Load the reviewed parent to prove its heuristic accepted known bypasses."""
    parent_script = tmp_path / "parent-guard.py"
    parent_script.write_bytes(
        subprocess.check_output(
            ["git", "show", "11ac6d9e9d27677d06d513364f2e658f5ed99870:.github/scripts/check-release-process-guards.py"],
            cwd=REPO_ROOT,
        )
    )
    spec = importlib.util.spec_from_file_location("reviewed_parent_guard", parent_script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parent_bypass_workflow(extra: str) -> str:
    return f'''workflows:
  omi-desktop-swift-release:
    scripts: &desktop_signed_artifact_steps
      - name: Smoke signed desktop artifact
        script: echo smoke
      - name: Create GitHub release
        script: |
          curl --request POST /v2/desktop/beta/candidates/reserve
          gh release create "$CM_TAG"
          {extra}
  omi-desktop-swift-preview:
    environment:
      vars:
        PREVIEW_MODE: "true"
    scripts: *desktop_signed_artifact_steps
'''


@pytest.mark.parametrize(
    "mutation",
    (
        'X=gh; $X release create "$TAG_NAME"',
        '${X:-gh} release create "$TAG_NAME"',
        'R=release; gh "$R" create "$TAG_NAME"',
        'gh r$(printf elease) create "$TAG_NAME"',
        'gh release c$(printf reate) "$TAG_NAME"',
        'echo harmless#$(X=gh; $X release create "$TAG_NAME")',
        'curl -X POST https://api.github.com/repos/BasedHardware/omi/releases',
    ),
)
def test_exact_contract_rejects_constructed_or_api_release_authority(tmp_path, monkeypatch, mutation):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        '          gh release create "$CM_TAG" \\\n',
        f'          {mutation}\n          gh release create "$CM_TAG" \\\n',
    )
    _assert_contract_rejects(errors)


@pytest.mark.parametrize(
    "replacement",
    (
        "false && curl --fail-with-body --silent --show-error \\",
        "if false; then curl --fail-with-body --silent --show-error; fi\n            curl --fail-with-body --silent --show-error \\",
        "curl() { echo decoy; }\n            curl --fail-with-body --silent --show-error \\",
    ),
)
def test_exact_contract_rejects_suppressed_or_shadowed_reservation(tmp_path, monkeypatch, replacement):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        "            curl --fail-with-body --silent --show-error \\",
        f"            {replacement}",
    )
    _assert_contract_rejects(errors)


def test_exact_contract_rejects_preview_alias_without_early_exit(tmp_path, monkeypatch):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        '          if [[ "${PREVIEW_MODE:-false}" == "true" ]]; then\n            echo "External previews do not create GitHub releases."\n            exit 0\n          fi\n',
        "",
    )
    _assert_contract_rejects(errors)
    assert any("preview publication script" in error for error in errors)


def test_exact_contract_rejects_preview_release_credentials(tmp_path, monkeypatch):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        "        - desktop_preview_secrets\n",
        "        - desktop_preview_secrets\n        - desktop_secrets\n",
    )
    _assert_contract_rejects(errors)
    assert any("normal release credential" in error for error in errors)


def test_exact_contract_rejects_another_workflow_importing_release_credentials(tmp_path, monkeypatch):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        "  omi-desktop-swift-preview:\n",
        "  unrelated:\n    environment:\n      groups:\n        - desktop_secrets\n    scripts: []\n\n  omi-desktop-swift-preview:\n",
    )
    assert any("unrelated imports normal release credential" in error for error in errors)


@pytest.mark.parametrize("token_name", ("GH_TOKEN", "GITHUB_TOKEN"))
def test_exact_contract_rejects_github_tokens_outside_canonical(tmp_path, monkeypatch, token_name):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        '        PREVIEW_MODE: "true"\n',
        f'        PREVIEW_MODE: "true"\n        {token_name}: shadow\n',
    )
    assert any(f"exposes {token_name} outside canonical" in error for error in errors)


def test_exact_contract_rejects_semantic_mutation_elsewhere_in_canonical_workflow(tmp_path, monkeypatch):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        "    max_build_duration: 120\n    environment:\n      groups:\n        - app_env\n",
        "    max_build_duration: 121\n    environment:\n      groups:\n        - app_env\n",
    )
    _assert_contract_rejects(errors)


def test_exact_contract_requires_shared_preview_script_node_not_a_copy(tmp_path, monkeypatch):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        "    scripts: *desktop_signed_artifact_steps\n",
        "    scripts:\n      - name: copied\n        script: echo copied\n",
    )
    assert any("exact YAML alias node" in error or "anchor and alias" in error for error in errors)


@pytest.mark.parametrize(
    "mutation, expected",
    (
        ("    <<: *desktop_signed_artifact_steps\n", "merge keys"),
        ("    name: !!str Release OMI Desktop (Swift)\n", "explicit YAML tags"),
        ("  omi-desktop-swift-release:\n    scripts: []\n", "duplicate key"),
    ),
)
def test_exact_contract_rejects_yaml_merge_tag_and_duplicate_collisions(tmp_path, monkeypatch, mutation, expected):
    errors = _errors_after(
        tmp_path,
        monkeypatch,
        "  omi-desktop-swift-preview:\n",
        f"{mutation}  omi-desktop-swift-preview:\n",
    )
    assert any(expected in error for error in errors), errors


@pytest.mark.parametrize(
    "bypass",
    (
        'X=gh; $X release create "$TAG_NAME"',
        '${X:-gh} release create "$TAG_NAME"',
        'R=release; gh "$R" create "$TAG_NAME"',
        'gh r$(printf elease) create "$TAG_NAME"',
        'gh release c$(printf reate) "$TAG_NAME"',
        'echo harmless#$(X=gh; $X release create "$TAG_NAME")',
        "curl -X POST https://api.github.com/repos/BasedHardware/omi/releases",
    ),
)
def test_reviewed_parent_accepts_constructed_release_and_api_bypasses(tmp_path, bypass):
    parent = _load_parent_guard(tmp_path)
    (tmp_path / "codemagic.yaml").write_text(_parent_bypass_workflow(bypass), encoding="utf-8")
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == [], bypass


@pytest.mark.parametrize(
    "replacement",
    (
        "false && curl --request POST /v2/desktop/beta/candidates/reserve",
        "if false; then curl --request POST /v2/desktop/beta/candidates/reserve; fi",
        "curl() { echo decoy; }\n          curl --request POST /v2/desktop/beta/candidates/reserve",
    ),
)
def test_reviewed_parent_accepts_suppressed_or_shadowed_reservations(tmp_path, replacement):
    parent = _load_parent_guard(tmp_path)
    workflow = _parent_bypass_workflow("echo harmless").replace(
        "curl --request POST /v2/desktop/beta/candidates/reserve", replacement, 1
    )
    (tmp_path / "codemagic.yaml").write_text(workflow, encoding="utf-8")
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == [], replacement


def test_reviewed_parent_accepts_preview_alias_without_early_exit(tmp_path):
    parent = _load_parent_guard(tmp_path)
    (tmp_path / "codemagic.yaml").write_text(_parent_bypass_workflow("echo harmless"), encoding="utf-8")
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == []


def test_codemagic_workflow_contract_accepts_current_production_configuration():
    assert GUARDS.check_codemagic_release_publishers() == []
