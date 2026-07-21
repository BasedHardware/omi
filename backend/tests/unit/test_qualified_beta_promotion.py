import hashlib
import io
import json
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from routers.updates import router as updates_router
from utils.qualified_beta_promotion import (
    MAX_QUALIFICATION_ARTIFACT_BYTES,
    REPOSITORY,
    GitHubQualifiedBetaReader,
    QualifiedBetaAdmissionError,
    _timestamp,
    build_qualified_beta_manifest,
)

_test_app = FastAPI()
_test_app.include_router(updates_router)

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
                "archive_download_url": "https://api.github.com/repos/BasedHardware/omi/actions/artifacts/456/zip",
            }
        ]
        self.artifact_downloads = {456: artifact}
        self.artifact_run_ids = []
        self.download_calls = []

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
        self.download_calls.append(url)
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


def _replace_trusted_evidence(reader, evidence):
    """Keep the immutable release copy and trusted artifact copy in sync for a probe."""
    evidence_bytes = json.dumps(evidence).encode()
    evidence_asset = reader.release_payload["assets"][2]
    reader.downloaded[evidence_asset["browser_download_url"]] = evidence_bytes
    evidence_asset["digest"] = _digest(evidence_bytes)
    artifact = _artifact_archive(evidence_bytes)
    reader.artifacts_payload[0]["size_in_bytes"] = len(artifact)
    reader.artifact_downloads[reader.artifacts_payload[0]["id"]] = artifact


def _malformed_reader(collection, value):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    if collection == "assets":
        reader.release_payload["assets"] = [value]
    elif collection == "runs":
        reader.runs_payload = [value]
    else:
        reader.artifacts_payload = [value]
    return reader


def _reader_with_malformed_member(collection, value):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    if collection == "assets":
        reader.release_payload["assets"].append(value)
    elif collection == "runs":
        reader.runs_payload.append(value)
    else:
        reader.artifacts_payload.append(value)
    return reader


async def _assert_direct_and_endpoint_rejection(reader):
    with pytest.raises(QualifiedBetaAdmissionError):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )

    with (
        patch.dict("os.environ", {"BETA_PROMOTION_TOKEN": "promotion-token"}),
        patch("utils.qualified_beta_promotion.GitHubQualifiedBetaReader", return_value=reader),
        patch("routers.updates.admit_qualified_beta_manifest") as admit,
        patch("routers.updates.delete_generic_cache") as invalidate,
    ):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            response = await client.post(
                "/v2/desktop/beta/promote-qualified",
                headers={"Authorization": "Bearer promotion-token"},
                json={"tag": TAG},
            )

    assert response.status_code == 422
    assert response.json() == {"detail": "Qualified Beta candidate rejected"}
    admit.assert_not_called()
    invalidate.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-21Z",
        "2026-07-21T12:00Z",
        "2026-07-21T12:00:00.Z",
        "2026-07-21T12:00:00.1234567Z",
        "2026-07-21T12:00:00,1Z",
        "2026-07-21T12:00:00",
        "2026-07-21T12:00:00+00:00",
        "2026-07-21T12:00:00+00:00Z",
        "2026-02-30T12:00:00Z",
        "2026-07-21T24:00:00Z",
        "2026-07-21T12:00:60Z",
    ],
)
def test_timestamp_requires_canonical_utc_rfc3339(value):
    with pytest.raises(QualifiedBetaAdmissionError):
        _timestamp(value)


@pytest.mark.parametrize(
    "value",
    ["2026-07-21T12:00:00Z", "2026-07-21T12:00:00.1Z", "2026-07-21T12:00:00.123456Z"],
)
def test_timestamp_accepts_canonical_utc_rfc3339_seconds_and_bounded_fractions(value):
    parsed = _timestamp(value)

    assert parsed.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_naive_admission_clock_is_a_typed_rejection_and_aware_offsets_normalize_to_utc():
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)

    with pytest.raises(QualifiedBetaAdmissionError):
        await build_qualified_beta_manifest(TAG, reader=reader, now=datetime(2026, 7, 21, 12, 2))

    manifest = await build_qualified_beta_manifest(
        TAG,
        reader=reader,
        now=datetime(2026, 7, 21, 8, 2, tzinfo=timezone(timedelta(hours=-4))),
    )

    assert manifest["release_id"] == TAG


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["published_at", "updated_at"],
)
@pytest.mark.parametrize(
    "value",
    [
        "2026-07-21Z",
        "2026-07-21T12:00Z",
        "2026-07-21T12:00:00.Z",
        "2026-07-21T12:00:00.1234567Z",
        "2026-07-21T12:00:00,1Z",
        "2026-07-21T12:00:00",
        "2026-07-21T12:00:00+00:00",
        "2026-07-21T12:00:00+00:00Z",
        "2026-02-30T12:00:00Z",
        "2026-07-21T24:00:00Z",
        "2026-07-21T12:00:60Z",
    ],
)
async def test_noncanonical_freshness_timestamps_reject_directly_and_at_endpoint_before_mutation(field, value):
    release, evidence, run = _candidate()
    if field == "published_at":
        release[field] = value
    else:
        run[field] = value
    reader = FakeQualifiedBetaReader(release, evidence, run)

    with pytest.raises(QualifiedBetaAdmissionError):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )

    with (
        patch.dict("os.environ", {"BETA_PROMOTION_TOKEN": "promotion-token"}),
        patch("utils.qualified_beta_promotion.GitHubQualifiedBetaReader", return_value=reader),
        patch("routers.updates.admit_qualified_beta_manifest") as admit,
        patch("routers.updates.delete_generic_cache") as invalidate,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v2/desktop/beta/promote-qualified",
                headers={"Authorization": "Bearer promotion-token"},
                json={"tag": TAG},
            )

    assert (response.status_code, admit.call_count, invalidate.call_count) == (422, 0, 0)


@pytest.mark.asyncio
async def test_date_only_z_run_timestamp_is_a_typed_direct_rejection_not_a_raw_type_error():
    release, evidence, run = _candidate()
    run["updated_at"] = "2026-07-21Z"

    with pytest.raises(QualifiedBetaAdmissionError):
        await build_qualified_beta_manifest(
            TAG,
            reader=FakeQualifiedBetaReader(release, evidence, run),
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["published_at", "updated_at"])
async def test_future_freshness_timestamps_reject_directly_and_at_endpoint_before_mutation(field):
    release, evidence, run = _candidate()
    if field == "published_at":
        release[field] = "2027-07-21T12:01:00Z"
    else:
        run[field] = "2027-07-21T12:01:00Z"
    reader = FakeQualifiedBetaReader(release, evidence, run)

    with pytest.raises(QualifiedBetaAdmissionError):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )

    receipt = {"manifest": {"release_id": TAG}, "pointer": {"generation": 1}, "idempotent": False}
    with (
        patch.dict("os.environ", {"BETA_PROMOTION_TOKEN": "promotion-token"}),
        patch("utils.qualified_beta_promotion.GitHubQualifiedBetaReader", return_value=reader),
        patch("routers.updates.admit_qualified_beta_manifest", return_value=receipt) as admit,
        patch("routers.updates.delete_generic_cache") as invalidate,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=_test_app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v2/desktop/beta/promote-qualified",
                headers={"Authorization": "Bearer promotion-token"},
                json={"tag": TAG},
            )

    assert (response.status_code, admit.call_count, invalidate.call_count) == (422, 0, 0)


def _corrupt_deflated_artifact(evidence):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("qualification-evidence.json", evidence)
    payload = bytearray(output.getvalue())
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.getinfo("qualification-evidence.json")
    data_offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    payload[data_offset : data_offset + info.compress_size] = b"\xff" * info.compress_size
    return bytes(payload)


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
@pytest.mark.parametrize(
    ("field", "expected_error"),
    [
        ("qualification_run_id", "does not bind its run"),
        ("run_id", "qualification run has no trusted identity"),
        ("artifact_id", "qualification artifact is invalid"),
        ("artifact_size", "qualification artifact is invalid"),
        ("evidence_schema_version", "trusted qualification evidence is invalid"),
    ],
)
async def test_boolean_security_integer_metadata_is_rejected(field, expected_error):
    release, evidence_bytes, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence_bytes, run)

    if field == "qualification_run_id":
        run["id"] = 1
        evidence = json.loads(evidence_bytes)
        evidence["qualification_run_id"] = True
        _replace_trusted_evidence(reader, evidence)
    elif field == "run_id":
        run["id"] = True
    elif field == "artifact_id":
        reader.artifacts_payload[0]["id"] = True
        reader.artifact_downloads[True] = reader.artifact_downloads.pop(456)
    elif field == "artifact_size":
        reader.artifacts_payload[0]["size_in_bytes"] = True
    else:
        evidence = json.loads(evidence_bytes)
        evidence["schema_version"] = True
        _replace_trusted_evidence(reader, evidence)

    with pytest.raises(QualifiedBetaAdmissionError, match=expected_error):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["assets", "runs", "artifacts"])
@pytest.mark.parametrize("value", [None, "not-an-object", [], {}])
async def test_malformed_nested_github_entries_are_typed_admission_rejections(collection, value):
    reader = _malformed_reader(collection, value)

    with pytest.raises(QualifiedBetaAdmissionError):
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", [{}, [], None, True, 1])
async def test_malformed_release_asset_names_fail_closed_before_set_construction(name):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.release_payload["assets"].append(
        {
            "name": name,
            "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{TAG}/unrelated.bin",
            "digest": _digest(b"unrelated"),
        }
    )

    await _assert_direct_and_endpoint_rejection(reader)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["draft", "prerelease"])
@pytest.mark.parametrize(
    "value",
    [None, 0, 0.0, "", [], {}, 1, 1.0, "false", [False], {"truthy": True}],
)
async def test_non_boolean_release_state_shapes_fail_closed_before_admission(field, value):
    release, evidence, run = _candidate()
    release[field] = value

    await _assert_direct_and_endpoint_rejection(FakeQualifiedBetaReader(release, evidence, run))


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, 0, {}, [], 1, {"merged": True}, [True]])
async def test_non_boolean_merge_state_fails_closed_before_run_selection(value):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.merged = value

    await _assert_direct_and_endpoint_rejection(reader)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collection", "value"),
    [
        ("assets", {}),
        ("assets", "not-an-object"),
        ("assets", {"name": 1, "browser_download_url": "invalid", "digest": "invalid"}),
        ("assets", {"name": "unrelated.bin"}),
        ("runs", {}),
        ("runs", "not-an-object"),
        ("runs", {"id": True}),
        ("runs", {key: value for key, value in _candidate()[2].items() if key != "updated_at"}),
        ("artifacts", {}),
        ("artifacts", "not-an-object"),
        ("artifacts", {"id": True}),
        (
            "artifacts",
            {
                key: value
                for key, value in FakeQualifiedBetaReader(*_candidate()).artifacts_payload[0].items()
                if key != "archive_download_url"
            },
        ),
    ],
)
async def test_malformed_members_mixed_with_valid_github_collections_fail_closed(collection, value):
    await _assert_direct_and_endpoint_rejection(_reader_with_malformed_member(collection, value))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", 1),
        ("browser_download_url", []),
        ("digest", []),
    ],
)
async def test_every_consumed_release_asset_field_is_checked_for_mixed_members(field, value):
    release, evidence, run = _candidate()
    malformed = {
        "name": "unrelated.bin",
        "browser_download_url": f"https://github.com/{REPOSITORY}/releases/download/{TAG}/unrelated.bin",
        "digest": _digest(b"unrelated"),
    }
    malformed[field] = value
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.release_payload["assets"].append(malformed)

    await _assert_direct_and_endpoint_rejection(reader)


@pytest.mark.asyncio
async def test_malformed_timestamp_in_otherwise_trusted_run_rejects_before_endpoint_mutation():
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.runs_payload.append({**run, "id": 124, "updated_at": "not-a-date"})

    direct_rejected = False
    try:
        await build_qualified_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
        )
    except QualifiedBetaAdmissionError:
        direct_rejected = True

    with (
        patch.dict("os.environ", {"BETA_PROMOTION_TOKEN": "promotion-token"}),
        patch("utils.qualified_beta_promotion.GitHubQualifiedBetaReader", return_value=reader),
        patch("routers.updates.admit_qualified_beta_manifest") as admit,
        patch("routers.updates.delete_generic_cache") as invalidate,
    ):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            response = await client.post(
                "/v2/desktop/beta/promote-qualified",
                headers={"Authorization": "Bearer promotion-token"},
                json={"tag": TAG},
            )

    assert (response.status_code, admit.call_count, invalidate.call_count) == (422, 0, 0)
    assert response.json() == {"detail": "Qualified Beta candidate rejected"}
    assert direct_rejected is True
    admit.assert_not_called()
    invalidate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unrelated_member",
    [
        (
            "assets",
            {"name": "unrelated.bin", "browser_download_url": "https://example.test/unrelated.bin", "digest": None},
        ),
        ("runs", {**_candidate()[2], "id": 124, "name": None}),
        ("runs", {key: value for key, value in {**_candidate()[2], "id": 124}.items() if key != "name"}),
        ("runs", {**_candidate()[2], "id": 124, "head_branch": None}),
        (
            "artifacts",
            {
                "id": 457,
                "name": "unrelated-artifact",
                "expired": False,
                "size_in_bytes": 0,
                "archive_download_url": "https://api.github.com/repos/BasedHardware/omi/actions/artifacts/457/zip",
            },
        ),
    ],
)
async def test_documented_unrelated_github_member_shapes_do_not_reject_a_valid_candidate(unrelated_member):
    collection, member = unrelated_member
    reader = _reader_with_malformed_member(collection, member)

    manifest = await build_qualified_beta_manifest(
        TAG,
        reader=reader,
        now=datetime(2026, 7, 21, 12, 2, tzinfo=timezone.utc),
    )

    assert manifest["release_id"] == TAG


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("status", 1),
        ("conclusion", []),
        ("event", {}),
        ("path", None),
        ("head_branch", 1),
        ("head_sha", []),
        ("name", {}),
        ("updated_at", None),
        ("repository", {"full_name": 1}),
        ("head_repository", {"full_name": []}),
    ],
)
async def test_every_consumed_qualification_run_field_is_checked_for_mixed_members(field, value):
    release, evidence, run = _candidate()
    malformed = {**run, field: value}
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.runs_payload.append(malformed)

    await _assert_direct_and_endpoint_rejection(reader)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("name", 1),
        ("expired", 0),
        ("size_in_bytes", True),
        ("archive_download_url", []),
    ],
)
async def test_every_consumed_qualification_artifact_field_is_checked_for_mixed_members(field, value):
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    malformed = {**reader.artifacts_payload[0], field: value}
    reader.artifacts_payload.append(malformed)

    await _assert_direct_and_endpoint_rejection(reader)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("collection", "value"),
    [
        ("assets", None),
        ("assets", "not-an-object"),
        ("assets", []),
        ("assets", {}),
        ("runs", None),
        ("runs", "not-an-object"),
        ("runs", []),
        ("runs", {}),
        ("artifacts", None),
        ("artifacts", "not-an-object"),
        ("artifacts", []),
        ("artifacts", {}),
    ],
)
async def test_malformed_nested_metadata_returns_generic_422_without_mutation(collection, value):
    reader = _malformed_reader(collection, value)

    with (
        patch.dict("os.environ", {"BETA_PROMOTION_TOKEN": "promotion-token"}),
        patch("utils.qualified_beta_promotion.GitHubQualifiedBetaReader", return_value=reader),
        patch("routers.updates.admit_qualified_beta_manifest") as admit,
        patch("routers.updates.delete_generic_cache") as invalidate,
    ):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            response = await client.post(
                "/v2/desktop/beta/promote-qualified",
                headers={"Authorization": "Bearer promotion-token"},
                json={"tag": TAG},
            )

    assert response.status_code == 422
    assert response.json() == {"detail": "Qualified Beta candidate rejected"}
    admit.assert_not_called()
    invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_uncompleted_qualification_run_fails_before_any_mutation_can_begin():
    release, evidence, run = _candidate()
    run.pop("status")

    with pytest.raises(QualifiedBetaAdmissionError, match="qualification runs are invalid"):
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
            "archive_download_url": "https://api.github.com/repos/BasedHardware/omi/actions/artifacts/456/zip",
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
async def test_corrupted_deflated_artifact_returns_typed_rejection_without_post_rejection_side_effects():
    release, evidence, run = _candidate()
    reader = FakeQualifiedBetaReader(release, evidence, run)
    reader.artifact_downloads[456] = _corrupt_deflated_artifact(evidence)
    with zipfile.ZipFile(io.BytesIO(reader.artifact_downloads[456])) as archive:
        with pytest.raises(zlib.error):
            archive.read("qualification-evidence.json")

    with (
        patch.dict("os.environ", {"BETA_PROMOTION_TOKEN": "promotion-token"}),
        patch("utils.qualified_beta_promotion.GitHubQualifiedBetaReader", return_value=reader),
        patch("routers.updates.admit_qualified_beta_manifest") as admit,
        patch("routers.updates.delete_generic_cache") as invalidate,
    ):
        async with AsyncClient(transport=ASGITransport(app=_test_app), base_url="http://test") as client:
            response = await client.post(
                "/v2/desktop/beta/promote-qualified",
                headers={"Authorization": "Bearer promotion-token"},
                json={"tag": TAG},
            )

    assert response.status_code == 422
    assert response.json() == {"detail": "Qualified Beta candidate rejected"}
    assert reader.download_calls == []
    assert admit.call_count == 0
    assert invalidate.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "artifacts",
    [
        [],
        [
            {
                "id": 456,
                "name": f"desktop-qualification-evidence-{TAG}",
                "expired": False,
                "size_in_bytes": 1,
                "archive_download_url": "https://api.github.com/repos/BasedHardware/omi/actions/artifacts/456/zip",
            },
            {
                "id": 457,
                "name": f"desktop-qualification-evidence-{TAG}",
                "expired": False,
                "size_in_bytes": 1,
                "archive_download_url": "https://api.github.com/repos/BasedHardware/omi/actions/artifacts/457/zip",
            },
        ],
        [
            {
                "id": 456,
                "name": f"desktop-qualification-evidence-{TAG}",
                "expired": True,
                "size_in_bytes": 1,
                "archive_download_url": "https://api.github.com/repos/BasedHardware/omi/actions/artifacts/456/zip",
            }
        ],
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
