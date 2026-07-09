import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / ".github" / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mark_beta = _load("mark_desktop_release_beta", "mark-desktop-release-beta.py")
prepare_beta = _load("prepare_desktop_beta_promotion", "prepare-desktop-beta-promotion.py")


def _release(body: str | None = None):
    tag = "v0.12.64+12064-macos"
    evidence = "bless-evidence.json"
    default_body = f"""<!-- KEY_VALUE_START
isLive: false
channel: candidate
edSignature: signature
changelog: Fixed updates|Improved recovery
blessed: true
blessedAt: 2026-07-09T12:00:00Z
blessedSha: {'a' * 40}
blessedTier: 2
blessedEvidence: {evidence}
KEY_VALUE_END -->"""
    return {
        "tagName": tag,
        "body": default_body if body is None else body,
        "isDraft": False,
        "isPrerelease": False,
        "publishedAt": "2026-07-09T11:00:00Z",
        "assets": [
            {"name": "Omi.zip", "url": "https://example.com/Omi.zip"},
            {"name": "omi.dmg", "url": "https://example.com/omi.dmg"},
            {"name": evidence, "url": "https://example.com/evidence.json"},
        ],
    }


def test_mark_beta_changes_only_visibility_fields():
    result = mark_beta.mark_beta(_release()["body"])
    assert "isLive: true" in result
    assert "channel: beta" in result
    assert "blessedSha: " + "a" * 40 in result


def test_prepare_manifest_requires_exact_qualification_and_assets():
    manifest = prepare_beta.prepare_manifest(
        _release(),
        "v0.12.64+12064-macos",
        "a" * 40,
        "b" * 64,
        "c" * 64,
    )
    assert manifest["build_number"] == 12064
    assert manifest["qualification"]["tier"] == "T2"
    assert manifest["changelog"] == ["Fixed updates", "Improved recovery"]


def test_prepare_manifest_rejects_unblessed_candidate():
    release = _release()
    release["body"] = release["body"].replace("blessed: true", "blessed: false")
    with pytest.raises(SystemExit, match="blessed"):
        prepare_beta.prepare_manifest(
            release,
            "v0.12.64+12064-macos",
            "a" * 40,
            "b" * 64,
            "c" * 64,
        )
