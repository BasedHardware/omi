from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / ".github/scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


APPCAST = _load("verify_stable_appcast.py")
POINTER = _load("check_stable_pointer_precondition.py")


def _fields(release_id: str, generation: int) -> dict:
    return {"release_id": {"stringValue": release_id}, "generation": {"integerValue": str(generation)}}


def test_lost_response_retry_accepts_only_the_expected_next_generation():
    POINTER.verify(beta=_fields("target", 4), stable=_fields("target", 8), release_id="target", expected_release_id="previous", expected_generation=7, operation="promote")
    with pytest.raises(ValueError, match="unrelated generation drift"):
        POINTER.verify(beta=_fields("target", 4), stable=_fields("target", 9), release_id="target", expected_release_id="previous", expected_generation=7, operation="promote")


def test_stable_appcast_ignores_beta_item_but_rejects_two_default_items(tmp_path):
    manifest = {"build_number": 9, "version": "1.0", "zip_url": "https://example.test/Omi.zip", "ed_signature": "sig"}
    feed = tmp_path / "feed.xml"
    feed.write_text('''<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel>
<item><enclosure url="https://example.test/Omi.zip" sparkle:edSignature="sig"/><sparkle:version>9</sparkle:version><sparkle:shortVersionString>1.0</sparkle:shortVersionString></item>
<item><enclosure url="https://example.test/Omi.zip" sparkle:edSignature="sig"/><sparkle:version>9</sparkle:version><sparkle:shortVersionString>1.0</sparkle:shortVersionString><sparkle:channel>beta</sparkle:channel></item></channel></rss>''')
    APPCAST.verify(manifest, feed)
    feed.write_text(feed.read_text().replace("<sparkle:channel>beta</sparkle:channel>", ""))
    with pytest.raises(ValueError, match="default/non-beta"):
        APPCAST.verify(manifest, feed)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
