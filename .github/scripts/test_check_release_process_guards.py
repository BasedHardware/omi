from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

SCRIPT = Path(__file__).with_name("check-release-process-guards.py")
REPO_ROOT = SCRIPT.parents[2]
SPEC = importlib.util.spec_from_file_location("check_release_process_guards", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
GUARDS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARDS)
REVIEWED_PARENT = "4e391ee726642d99abc2c61966dcd80a836e6c1c"
RAW_SCANNER_PARENT = "11ac6d9e9d27677d06d513364f2e658f5ed99870"


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


def _load_parent_guard(tmp_path: Path, revision: str = REVIEWED_PARENT):
    """Load the reviewed parent to prove its narrower lock accepted known bypasses."""
    parent_script = tmp_path / "parent-guard.py"
    parent_script.write_bytes(
        subprocess.check_output(
            ["git", "show", f"{revision}:.github/scripts/check-release-process-guards.py"],
            cwd=REPO_ROOT,
        )
    )
    spec = importlib.util.spec_from_file_location("reviewed_parent_guard", parent_script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _append_unreviewed_workflow(
    path: Path, script: str, *, credential_group: str = "alternate_release_credentials"
) -> None:
    indented_script = script.replace("\n", "\n          ")
    path.write_text(
        path.read_text(encoding="utf-8") + f"""\n  unreviewed-publisher:
    environment:
      groups:
        - {credential_group}
    scripts:
      - name: Unreviewed publisher
        script: |
          {indented_script}
""",
        encoding="utf-8",
    )


def _fixture_path(root: Path) -> Path:
    return root / ".github/scripts/fixtures/codemagic_workflow_contract/v1.json"


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
    parent = _load_parent_guard(tmp_path, RAW_SCANNER_PARENT)
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
    parent = _load_parent_guard(tmp_path, RAW_SCANNER_PARENT)
    workflow = _parent_bypass_workflow("echo harmless").replace(
        "curl --request POST /v2/desktop/beta/candidates/reserve", replacement, 1
    )
    (tmp_path / "codemagic.yaml").write_text(workflow, encoding="utf-8")
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == [], replacement


def test_reviewed_parent_accepts_preview_alias_without_early_exit(tmp_path):
    parent = _load_parent_guard(tmp_path, RAW_SCANNER_PARENT)
    (tmp_path / "codemagic.yaml").write_text(_parent_bypass_workflow("echo harmless"), encoding="utf-8")
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == []


def test_codemagic_workflow_contract_accepts_current_production_configuration():
    assert GUARDS.check_codemagic_release_publishers() == []


@pytest.mark.parametrize(
    "script",
    (
        'X=gh; $X release create "$CM_TAG"',
        './release-publisher "$CM_TAG"',
        'python3 -c \'import subprocess; subprocess.run(["gh", "release", "create", "v0"])\'',
        'URL=https://api.github.com/repos/BasedHardware/omi/releases; curl -X POST "$URL"',
    ),
    ids=("shell-construction", "direct-wrapper", "python-construction", "variable-api-url"),
)
def test_reviewed_parent_accepts_unreviewed_publisher_bypasses_but_global_lock_rejects(tmp_path, monkeypatch, script):
    codemagic = _copy_contract_tree(tmp_path, monkeypatch)
    _append_unreviewed_workflow(codemagic, script)

    parent = _load_parent_guard(tmp_path)
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == [], script

    errors = GUARDS.check_codemagic_release_publishers()
    assert any("entire document" in error for error in errors), errors


def test_reviewed_parent_accepts_unknown_credential_group_with_publisher_but_global_lock_rejects(tmp_path, monkeypatch):
    codemagic = _copy_contract_tree(tmp_path, monkeypatch)
    _append_unreviewed_workflow(
        codemagic,
        'X=gh; $X release create "$CM_TAG"',
        credential_group="unrecognized_release_authority",
    )

    parent = _load_parent_guard(tmp_path)
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == []

    errors = GUARDS.check_codemagic_release_publishers()
    assert any("entire document" in error for error in errors), errors


@pytest.mark.parametrize(
    ("old", "new", "parent_accepts"),
    (
        (
            "    max_build_duration: 120\n    integrations:\n      app_store_connect: codemagic_v4\n",
            "    max_build_duration: 121\n    integrations:\n      app_store_connect: codemagic_v4\n",
            True,
        ),
        (
            "  # AUTO-DEPLOY WORKFLOWS (Triggered on push to main)\n",
            "  # This reviewed comment changes only raw source bytes.\n",
            True,
        ),
        (
            "&desktop_signed_artifact_steps",
            "&renamed_desktop_signed_artifact_steps",
            False,
        ),
        (
            "workflows:\n",
            "review_metadata: reviewed\nworkflows:\n",
            True,
        ),
    ),
    ids=("unrelated-workflow", "comment-bytes", "anchor-spelling", "top-level-field"),
)
def test_global_document_lock_rejects_every_codemagic_mutation(tmp_path, monkeypatch, old, new, parent_accepts):
    codemagic = _copy_contract_tree(tmp_path, monkeypatch)
    _mutate(codemagic, old, new)
    if old == "&desktop_signed_artifact_steps":
        _mutate(codemagic, "*desktop_signed_artifact_steps", "*renamed_desktop_signed_artifact_steps")

    parent = _load_parent_guard(tmp_path)
    parent.ROOT = tmp_path
    parent_errors = parent.check_codemagic_release_publishers()
    assert (parent_errors == []) is parent_accepts, parent_errors

    errors = GUARDS.check_codemagic_release_publishers()
    assert any("entire document" in error for error in errors), errors


def test_global_document_raw_lock_rejects_semantically_equivalent_yaml_rewrite(tmp_path, monkeypatch):
    codemagic = _copy_contract_tree(tmp_path, monkeypatch)
    _mutate(
        codemagic,
        "    name: Auto Deploy iOS to Internal TestFlight\n",
        '    name: "Auto Deploy iOS to Internal TestFlight"\n',
    )
    assert yaml.safe_load(codemagic.read_text(encoding="utf-8")) == yaml.safe_load(
        (REPO_ROOT / "codemagic.yaml").read_text(encoding="utf-8")
    )

    parent = _load_parent_guard(tmp_path)
    parent.ROOT = tmp_path
    assert parent.check_codemagic_release_publishers() == []

    errors = GUARDS.check_codemagic_release_publishers()
    assert any("raw byte digest" in error for error in errors), errors
    assert not any("semantic digest" in error for error in errors), errors


def test_global_document_semantic_lock_is_checked_even_when_raw_bytes_are_unchanged(tmp_path, monkeypatch):
    codemagic = _copy_contract_tree(tmp_path, monkeypatch)
    loaded = yaml.safe_load(codemagic.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    loaded["semantic_lock_test_seam"] = "changed only through the safe-load seam"
    monkeypatch.setattr(GUARDS, "_load_codemagic_with_duplicates", lambda _path: (loaded, [], []))

    errors = GUARDS.check_codemagic_release_publishers()
    assert not any("raw byte digest" in error for error in errors), errors
    assert any("semantic digest" in error for error in errors), errors


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("codemagic_raw_sha256", "0" * 64),
        ("codemagic_semantic_sha256", "0" * 64),
        ("codemagic_raw_sha256", None),
        ("codemagic_semantic_sha256", "not-a-sha256"),
    ),
    ids=("raw-tampered", "semantic-tampered", "raw-missing", "semantic-malformed"),
)
def test_global_document_lock_rejects_tampered_missing_or_malformed_fixture_digests(
    tmp_path, monkeypatch, field, value
):
    _copy_contract_tree(tmp_path, monkeypatch)
    fixture = _fixture_path(tmp_path)
    contract = json.loads(fixture.read_text(encoding="utf-8"))
    if value is None:
        del contract[field]
    else:
        contract[field] = value
    fixture.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")

    errors = GUARDS.check_codemagic_release_publishers()
    assert any("fixture" in error and field in error for error in errors), errors


def test_fixture_independently_hashes_only_current_codemagic_source():
    codemagic = REPO_ROOT / "codemagic.yaml"
    fixture = _fixture_path(REPO_ROOT)
    contract = json.loads(fixture.read_text(encoding="utf-8"))
    raw_bytes = codemagic.read_bytes()
    semantic_json = json.dumps(
        yaml.safe_load(raw_bytes.decode("utf-8")), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )

    assert contract["codemagic_raw_sha256"] == hashlib.sha256(raw_bytes).hexdigest()
    assert contract["codemagic_semantic_sha256"] == hashlib.sha256(semantic_json.encode("utf-8")).hexdigest()
    assert contract["codemagic_raw_sha256"] != hashlib.sha256(fixture.read_bytes()).hexdigest()
