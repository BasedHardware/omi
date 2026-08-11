import hashlib
import json
from datetime import datetime, timezone

import pytest

from utils.beta_breakglass_evidence import build_signed_beta_manifest
from utils.beta_candidate_evidence import BetaCandidateAdmissionError

TAG = "v0.12.159+12159-macos"
SHA = "a" * 40


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _url(name: str) -> str:
    return f"https://github.com/BasedHardware/omi/releases/download/{TAG}/{name}"


def _smoke() -> bytes:
    return json.dumps(
        {
            "ok": True,
            "release_tag": TAG,
            "source_sha": SHA,
            "expected_channel": "beta",
            "bundle_id": "com.omi.computer-macos.beta",
            "artifacts": [
                {"label": "sparkle_zip", "sha256": hashlib.sha256(b"beta zip").hexdigest()},
                {"label": "dmg", "sha256": hashlib.sha256(b"beta dmg").hexdigest()},
            ],
            "checks": ["Signed desktop artifact smoke completed"],
        }
    ).encode()


class FakeReader:
    def __init__(self) -> None:
        smoke = _smoke()
        payloads = {
            "Omi.zip": b"stable zip",
            "omi.dmg": b"stable dmg",
            "Omi.Beta.zip": b"beta zip",
            "omi-beta.dmg": b"beta dmg",
            "desktop-smoke-result-beta.json": smoke,
        }
        self.release_payload = {
            "tag_name": TAG,
            "draft": False,
            "prerelease": False,
            "published_at": "2026-08-11T12:00:00Z",
            "body": (
                "<!-- KEY_VALUE_START\nedSignature: stable-signature\n"
                "betaEdSignature: beta-signature\nchangelog: Automatic Beta\nKEY_VALUE_END -->"
            ),
            "assets": [
                {"name": name, "browser_download_url": _url(name), "digest": _digest(payload)}
                for name, payload in payloads.items()
            ],
        }
        self.downloads = {_url("desktop-smoke-result-beta.json"): smoke}

    async def release(self, tag: str):
        assert tag == TAG
        return self.release_payload

    async def tag_sha(self, tag: str):
        assert tag == TAG
        return SHA

    async def is_merged_source(self, source_sha: str):
        return source_sha == SHA

    async def download(self, url: str):
        return self.downloads[url]


@pytest.mark.asyncio
async def test_signed_beta_manifest_binds_exact_codemagic_beta_smoke_and_preserves_false_t2_truth():
    manifest = await build_signed_beta_manifest(
        TAG,
        reader=FakeReader(),
        now=datetime(2026, 8, 11, 12, 2, tzinfo=timezone.utc),
    )

    assert manifest["release_id"] == TAG
    assert manifest["qualification_tier"] == "signed-smoke"
    assert manifest["qualification_passed"] is False
    assert manifest["qualification_evidence_asset"] == "desktop-smoke-result-beta.json"


@pytest.mark.asyncio
async def test_signed_beta_manifest_rejects_smoke_that_does_not_match_published_beta_digest():
    reader = FakeReader()
    reader.release_payload["assets"][2]["digest"] = _digest(b"different beta zip")

    with pytest.raises(BetaCandidateAdmissionError, match="does not bind the published artifacts"):
        await build_signed_beta_manifest(
            TAG,
            reader=reader,
            now=datetime(2026, 8, 11, 12, 2, tzinfo=timezone.utc),
        )
