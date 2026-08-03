"""Coverage for the shared dev-only capture adapter used beyond listen."""

import base64
import json

from testing.parity_pack_v0.live_capture import SurfaceParityCapture


def _env(root):
    return {
        "OMI_ENV_STAGE": "dev",
        "OMI_PARITY_PACK_CAPTURE": "1",
        "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "allowed-user",
        "OMI_PARITY_PACK_ROOT": str(root),
    }


def _capture(root, *, principal_id="allowed-user"):
    return SurfaceParityCapture.from_environ(
        principal_id=principal_id,
        session_id="surface-session",
        surface="memory_write",
        source="memory_write",
        provider_lane="memory",
        route_or_model="memory-write",
        request={"row_count": 1},
        environ=_env(root),
    )


def test_surface_capture_persists_discriminators_and_redacts_text_payloads(tmp_path):
    capture = _capture(tmp_path)

    capture.observe(
        "client",
        {"type": "memory_rows", "email": "dogfood@example.com", "token": "do-not-keep"},
    )
    capture.persist()

    cassette = json.loads(next((tmp_path / "cassettes").glob("*.json")).read_text())
    assert cassette["surface"] == "memory_write"
    assert cassette["source"] == "memory_write"
    assert cassette["identity"]["anon_session"] != "allowed-user"
    assert cassette["events"][0]["payload"]["email"] == "[REDACTED_EMAIL]"
    assert cassette["events"][0]["payload"]["token"] == "[REDACTED]"


def test_surface_capture_preserves_binary_audio_encoding_and_denies_non_allowlisted_users(tmp_path):
    allowed = _capture(tmp_path)
    audio = b"12345678901234567890"
    allowed.observe_audio("client", audio)
    allowed.persist()

    cassette = json.loads(next((tmp_path / "cassettes").glob("*.json")).read_text())
    assert cassette["events"][0]["payload"]["audio_b64"] == base64.b64encode(audio).decode("ascii")

    denied = _capture(tmp_path / "denied", principal_id="not-allowlisted")
    denied.observe("client", {"must": "not-persist"})
    denied.persist()
    assert not (tmp_path / "denied" / "cassettes").exists()


def test_surface_capture_denies_screen_and_ocr_surfaces(tmp_path):
    for surface in ("screen", "screen_activity", "ocr_text"):
        capture = SurfaceParityCapture.from_environ(
            principal_id="allowed-user",
            session_id="surface-session",
            surface=surface,
            source=surface,
            provider_lane="screen",
            route_or_model=surface,
            request={"value": "secret"},
            environ=_env(tmp_path / surface),
        )
        assert not capture.enabled
        capture.observe("client", {"type": "screen_activity_rows", "value": "secret"})
        capture.persist()

    assert not list(tmp_path.glob("**/cassettes/*.json"))
