import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from utils.qualified_beta_promotion import (
    MAX_QUALIFICATION_ARTIFACT_BYTES,
    GitHubQualifiedBetaReader,
    QualifiedBetaAdmissionError,
    build_qualified_beta_manifest,
)

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
        self.runs_payload = [run]
        artifact = _artifact_archive(evidence)
        self.artifacts_payload = [
            {
                "id": 456,
                "name": f"desktop-qualification-evidence-{release['tag_name']}",
                "expired": False,
                "size_in_bytes": len(artifact),
            }
        ]
        self.artifact_downloads = {456: artifact}
        self.artifact_run_ids = []

    async def release(self, tag):
        return self.release_payload

    async def tag_sha(self, tag):
        return SHA

    async def is_merged_source(self, source_sha):
        return self.merged

    async def runs(self):
        return self.runs_payload

    async def artifacts(self, run_id):
        self.artifact_run_ids.append(run_id)
        return self.artifacts_payload

    async def download_artifact(self, artifact_id):
        return self.artifact_downloads[artifact_id]

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
        "id": 123,
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


def _artifact_archive(evidence):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("qualification-evidence.json", evidence)
    return output.getvalue()


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

    with pytest.raises(QualifiedBetaAdmissionError, match="no fresh trusted qualification run"):
        await build_qualified_beta_manifest(
            TAG,
            reader=FakeQualifiedBetaReader(release, evidence, run),
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_release_asset_replacement_with_self_consistent_release_evidence_is_rejected():
    release, trusted_evidence, run = _candidate()
    replacement_zip = b"replacement zip"
    replacement_dmg = b"replacement dmg"
    replacement_evidence = json.loads(trusted_evidence)
    replacement_evidence["artifacts"]["Omi.zip"]["sha256"] = hashlib.sha256(replacement_zip).hexdigest()
    replacement_evidence["artifacts"]["omi.dmg"]["sha256"] = hashlib.sha256(replacement_dmg).hexdigest()
    replacement_evidence_bytes = json.dumps(replacement_evidence).encode()
    release["assets"][0]["digest"] = _digest(replacement_zip)
    release["assets"][1]["digest"] = _digest(replacement_dmg)
    release["assets"][2]["digest"] = _digest(replacement_evidence_bytes)

    reader = FakeQualifiedBetaReader(release, replacement_evidence_bytes, run)
    reader.downloaded[release["assets"][0]["browser_download_url"]] = replacement_zip
    reader.downloaded[release["assets"][1]["browser_download_url"]] = replacement_dmg
    reader.runs_payload = [run]
    reader.artifacts_payload = [
        {
            "id": 456,
            "name": f"desktop-qualification-evidence-{TAG}",
            "expired": False,
            "size_in_bytes": len(_artifact_archive(trusted_evidence)),
        }
    ]
    reader.artifact_downloads[456] = _artifact_archive(trusted_evidence)

    with pytest.raises(QualifiedBetaAdmissionError, match="differs from its trusted run artifact"):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_evidence_from_another_successful_run_is_rejected():
    release, evidence, run = _candidate()
    other_evidence = json.loads(evidence)
    other_evidence["qualification_run_id"] = 999
    other_evidence_bytes = json.dumps(other_evidence).encode()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.runs_payload = [{**run, "id": 999, "updated_at": "2026-07-21T12:00:30Z"}, run]
    reader.artifact_downloads[456] = _artifact_archive(other_evidence_bytes)

    with pytest.raises(QualifiedBetaAdmissionError, match="does not bind its run"):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_newest_acceptable_trusted_run_is_selected_without_a_caller_run_id():
    release, evidence, run = _candidate()
    older_run = {**run, "id": 122, "updated_at": "2026-07-21T12:00:30Z"}
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.runs_payload = [older_run, run]

    await build_qualified_beta_manifest(
        TAG,
        reader=reader,
        now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
    )

    assert reader.artifact_run_ids == [123]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("archive", "error"),
    [
        (b"not a ZIP", "not a safe ZIP"),
        (_artifact_archive(b"{}") + b"trailing bytes", "does not bind its run"),
    ],
)
async def test_malformed_qualification_artifact_fails_closed(archive, error):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.artifact_downloads[456] = archive

    with pytest.raises(QualifiedBetaAdmissionError, match=error):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_zip_slip_or_oversized_qualification_artifact_fails_closed():
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as contents:
        contents.writestr("qualification-evidence.json", evidence)
        contents.writestr("../outside.json", b"unexpected")
    reader.artifact_downloads[456] = archive.getvalue()

    with pytest.raises(QualifiedBetaAdmissionError, match="unexpected contents"):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifacts",
    [
        [],
        [
            {"id": 456, "name": f"desktop-qualification-evidence-{TAG}", "expired": False, "size_in_bytes": 1},
            {"id": 457, "name": f"desktop-qualification-evidence-{TAG}", "expired": False, "size_in_bytes": 1},
        ],
        [{"id": 456, "name": f"desktop-qualification-evidence-{TAG}", "expired": True, "size_in_bytes": 1}],
    ],
)
async def test_missing_ambiguous_or_expired_qualification_artifact_fails_closed(artifacts):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.artifacts_payload = artifacts

    with pytest.raises(QualifiedBetaAdmissionError, match="artifact is missing or ambiguous|artifact is expired"):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )

    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.artifacts_payload[0]["size_in_bytes"] = MAX_QUALIFICATION_ARTIFACT_BYTES + 1
    with pytest.raises(QualifiedBetaAdmissionError, match="artifact is invalid"):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_read_dependency_error_fails_closed_before_admission():
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)

    async def unavailable():
        raise RuntimeError("offline")

    reader.runs = unavailable
    with pytest.raises(QualifiedBetaAdmissionError, match="read dependency is unavailable"):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_missing_github_read_token_fails_closed(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(QualifiedBetaAdmissionError, match="read authorization is unavailable"):
        await GitHubQualifiedBetaReader().release(TAG)
