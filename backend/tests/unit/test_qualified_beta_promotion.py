import hashlib
import json
from datetime import datetime, timezone

import pytest

from utils.qualified_beta_promotion import QualifiedBetaAdmissionError, build_qualified_beta_manifest

TAG = "v0.12.93+12093-macos"
SHA = "a" * 40


class FakeQualifiedBetaReader:
    def __init__(self, release, evidence, run):
        self.release_payload = release
        self.run_payload = run
        self.merged = True
        self.downloaded = {
            release["assets"][0]["browser_download_url"]: b"zip bytes",
            release["assets"][1]["browser_download_url"]: b"dmg bytes",
            release["assets"][2]["browser_download_url"]: evidence,
        }

    async def release(self, tag):
        return self.release_payload

    async def tag_sha(self, tag):
        return SHA

    async def is_merged_source(self, source_sha):
        return self.merged

    async def run(self, run_id):
        return self.run_payload

    async def download(self, url):
        return self.downloaded[url]


def _digest(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _candidate():
    zip_url = f"https://github.com/BasedHardware/omi/releases/download/{TAG}/Omi.zip"
    dmg_url = f"https://github.com/BasedHardware/omi/releases/download/{TAG}/omi.dmg"
    evidence_name = f"qualification-evidence-{TAG}.json"
    evidence_url = f"https://github.com/BasedHardware/omi/releases/download/{TAG}/{evidence_name}"
    evidence = {
        "schema_version": 1,
        "release_id": TAG,
        "source_sha": SHA,
        "qualification_run_id": 123,
        "source_qualification": {"passed": True, "tier": "T2", "subject": "source-built named-bundle"},
        "signed_artifact_verification": {"passed": True, "subject": "exact signed ZIP/DMG bytes"},
        "artifacts": {
            "Omi.zip": {"url": zip_url, "sha256": hashlib.sha256(b"zip bytes").hexdigest(), "signature": "sparkle"},
            "omi.dmg": {"url": dmg_url, "sha256": hashlib.sha256(b"dmg bytes").hexdigest()},
        },
    }
    evidence_bytes = json.dumps(evidence).encode()
    release = {
        "tag_name": TAG,
        "draft": False,
        "prerelease": False,
        "published_at": "2026-07-21T12:00:00Z",
        "body": "<!-- KEY_VALUE_START\nedSignature: sparkle\nchangelog: Qualified candidate\nKEY_VALUE_END -->",
        "assets": [
            {"name": "Omi.zip", "browser_download_url": zip_url, "digest": _digest(b"zip bytes")},
            {"name": "omi.dmg", "browser_download_url": dmg_url, "digest": _digest(b"dmg bytes")},
            {"name": evidence_name, "browser_download_url": evidence_url, "digest": _digest(evidence_bytes)},
        ],
    }
    run = {
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "BasedHardware/omi"},
        "head_repository": {"full_name": "BasedHardware/omi"},
        "event": "workflow_dispatch",
        "path": ".github/workflows/desktop_qualify_beta.yml",
        "head_branch": TAG,
        "head_sha": SHA,
        "name": "Qualify Desktop Beta Candidate",
        "updated_at": "2026-07-21T12:01:00Z",
    }
    return release, evidence_bytes, run


@pytest.mark.asyncio
async def test_server_builds_the_canonical_manifest_from_qualified_immutable_assets():
    release, evidence, run = _candidate()

    manifest = await build_qualified_beta_manifest(
        TAG,
        reader=FakeQualifiedBetaReader(release, evidence, run),
        now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
    )

    assert manifest["release_id"] == TAG
    assert manifest["zip_url"].endswith("/Omi.zip")
    assert manifest["dmg_url"].endswith("/omi.dmg")
    assert manifest["qualification_evidence_sha256"] == _digest(evidence)


@pytest.mark.asyncio
async def test_uncompleted_qualification_run_fails_before_any_mutation_can_begin():
    release, evidence, run = _candidate()
    run.pop("status")

    with pytest.raises(QualifiedBetaAdmissionError, match="qualification run is not trusted"):
        await build_qualified_beta_manifest(
            TAG,
            reader=FakeQualifiedBetaReader(release, evidence, run),
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )
