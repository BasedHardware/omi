import hashlib
import json
from datetime import datetime, timezone

import pytest

from utils.beta_breakglass_evidence import build_signed_beta_manifest
from utils.beta_candidate_evidence import BetaCandidateAdmissionError

TAG = "v0.12.159+12159-macos"
SHA = "a" * 40
NOW = datetime(2026, 8, 11, 12, 2, tzinfo=timezone.utc)
STRUCTURAL_CHECKS = [
    "Launch + identity metadata is aligned",
    "Auth persistence prerequisites: signing identity and Keychain-compatible entitlements are sane",
    "Backend routing config matches the declared external backend",
    "Sparkle/update metadata and authoritative ZIP artifacts are present",
    "Native helper/runtime bundle integrity passed",
    "Local storage/database package surface is present",
    "Signed desktop artifact smoke completed",
]
BEHAVIORAL_CHECKS = [
    "Signed app launches and remains alive",
    "Signed artifact Keychain write/read/delete canary passed",
    "Signed app relaunched for UserNotifications callback canary",
    "UserNotifications settings callback completion canary passed",
]


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _url(name: str) -> str:
    return f"https://github.com/BasedHardware/omi/releases/download/{TAG}/{name}"


def _smoke(bundle_id: str, zip_payload: bytes, dmg_payload: bytes, *, behavioral: bool) -> bytes:
    payload = {
        "ok": True,
        "release_tag": TAG,
        "source_sha": SHA,
        "expected_channel": "beta",
        "bundle_id": bundle_id,
        "version": "0.12.159",
        "build": "12159",
        "team_id": "9536L8KLMP",
        "artifacts": [
            {"label": "sparkle_zip", "sha256": hashlib.sha256(zip_payload).hexdigest()},
            {"label": "dmg", "sha256": hashlib.sha256(dmg_payload).hexdigest()},
        ],
        "checks": STRUCTURAL_CHECKS + (BEHAVIORAL_CHECKS if behavioral else []),
    }
    if behavioral:
        payload["notification_callback_canary"] = {
            "schema": 1,
            "event": "user-notifications-settings-callback-completed",
            "bundle_id": bundle_id,
            "main_actor": True,
            "validated": True,
            "authorization_status": 1,
        }
    return json.dumps(payload).encode()


class FakeReader:
    def __init__(self) -> None:
        stable_smoke = _smoke("com.omi.computer-macos", b"stable zip", b"stable dmg", behavioral=False)
        beta_smoke = _smoke("com.omi.computer-macos.beta", b"beta zip", b"beta dmg", behavioral=True)
        payloads = {
            "Omi.zip": b"stable zip",
            "omi.dmg": b"stable dmg",
            "Omi.Beta.zip": b"beta zip",
            "omi-beta.dmg": b"beta dmg",
            "desktop-smoke-result.json": stable_smoke,
            "desktop-smoke-result-beta.json": beta_smoke,
        }
        self.release_payload = {
            "tag_name": TAG,
            "draft": False,
            "prerelease": False,
            "published_at": "2026-08-11T12:00:00Z",
            "body": (
                "<!-- KEY_VALUE_START\nisLive: false\nchannel: candidate\nedSignature: stable-signature\n"
                "betaEdSignature: beta-signature\nchangelog: Automatic Beta\nKEY_VALUE_END -->"
            ),
            "assets": [
                {"name": name, "browser_download_url": _url(name), "digest": _digest(payload)}
                for name, payload in payloads.items()
            ],
        }
        self.downloads = {
            _url("desktop-smoke-result.json"): stable_smoke,
            _url("desktop-smoke-result-beta.json"): beta_smoke,
        }
        self.source_sha = SHA
        self.merged = True

    def asset(self, name: str) -> dict:
        return next(asset for asset in self.release_payload["assets"] if asset["name"] == name)

    async def release(self, tag: str):
        assert tag == TAG
        return self.release_payload

    async def tag_sha(self, tag: str):
        assert tag == TAG
        return self.source_sha

    async def is_merged_source(self, source_sha: str):
        return self.merged and source_sha == SHA

    async def download(self, url: str):
        return self.downloads[url]


@pytest.mark.asyncio
async def test_signed_beta_manifest_binds_both_codemagic_smoke_results_and_preserves_false_t2_truth():
    manifest = await build_signed_beta_manifest(TAG, reader=FakeReader(), now=NOW)

    assert manifest["release_id"] == TAG
    assert manifest["qualification_tier"] == "signed-smoke"
    assert manifest["qualification_passed"] is False
    assert manifest["qualification_evidence_asset"] == "desktop-smoke-result-beta.json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_name", "message"),
    [
        ("Omi.zip", "candidate stable identity smoke does not bind the published artifacts"),
        ("Omi.Beta.zip", "candidate smoke does not bind the published artifacts"),
    ],
)
async def test_signed_beta_manifest_rejects_artifacts_not_bound_by_their_smoke(asset_name: str, message: str):
    reader = FakeReader()
    reader.asset(asset_name)["digest"] = _digest(b"different artifact")

    with pytest.raises(BetaCandidateAdmissionError, match=message):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("release_field", ["draft", "prerelease"])
async def test_signed_beta_manifest_rejects_unpublished_release_states(release_field: str):
    reader = FakeReader()
    reader.release_payload[release_field] = True

    with pytest.raises(BetaCandidateAdmissionError, match="not an immutable published release"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
async def test_signed_beta_manifest_rejects_stale_candidate():
    reader = FakeReader()
    reader.release_payload["published_at"] = "2026-07-01T12:00:00Z"

    with pytest.raises(BetaCandidateAdmissionError, match="candidate release is stale"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
async def test_signed_beta_manifest_rejects_source_not_merged_to_main():
    reader = FakeReader()
    reader.merged = False

    with pytest.raises(BetaCandidateAdmissionError, match="source identity is not merged main"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
async def test_signed_beta_manifest_rejects_download_not_matching_github_smoke_digest():
    reader = FakeReader()
    reader.asset("desktop-smoke-result-beta.json")["digest"] = _digest(b"different smoke")

    with pytest.raises(BetaCandidateAdmissionError, match="signed-smoke digest does not match"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        "<!-- KEY_VALUE_START\nisLive: true\nchannel: candidate\nKEY_VALUE_END -->",
        "<!-- KEY_VALUE_START\nisLive: false\nchannel: stable\nKEY_VALUE_END -->",
    ],
)
async def test_signed_beta_manifest_rejects_non_candidate_release_metadata(body: str):
    reader = FakeReader()
    reader.release_payload["body"] = body

    with pytest.raises(BetaCandidateAdmissionError, match="not non-live candidate state"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
async def test_signed_beta_manifest_rejects_incomplete_beta_behavioral_smoke():
    reader = FakeReader()
    incomplete = json.loads(reader.downloads[_url("desktop-smoke-result-beta.json")])
    incomplete["checks"].remove("Signed artifact Keychain write/read/delete canary passed")
    payload = json.dumps(incomplete).encode()
    reader.downloads[_url("desktop-smoke-result-beta.json")] = payload
    reader.asset("desktop-smoke-result-beta.json")["digest"] = _digest(payload)

    with pytest.raises(BetaCandidateAdmissionError, match="signed-artifact smoke is incomplete"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_signature", ["edSignature", "betaEdSignature"])
async def test_signed_beta_manifest_rejects_incomplete_sparkle_signatures(missing_signature: str):
    reader = FakeReader()
    reader.release_payload["body"] = reader.release_payload["body"].replace(
        f"{missing_signature}: {'stable-signature' if missing_signature == 'edSignature' else 'beta-signature'}\n",
        "",
    )

    with pytest.raises(BetaCandidateAdmissionError, match="no complete Sparkle signatures"):
        await build_signed_beta_manifest(TAG, reader=reader, now=NOW)
