from __future__ import annotations

import socket
from pathlib import Path

import pytest

from testing.parity_pack_v0.manifest import PackCase, build_manifest
from testing.parity_pack_v0.capture import CaptureTap
from testing.parity_pack_v0.players import (
    CassetteTopologyError,
    InvocationTopology,
    LLMCassettePlayer,
    STTCassettePlayer,
)
from testing.parity_pack_v0.redaction import redact_value
from testing.parity_pack_v0.runner import UnexpectedEgress, hermetic_run
from testing.parity_pack_v0.schema import CassetteIdentity, RequestFingerprint
from testing.parity_pack_v0.whitelist import CaptureWhitelist


def test_identity_tuple_is_stable_and_complete() -> None:
    identity = CassetteIdentity("session-a", "llm", "gpt-test", 2, 1, "event-a")
    assert identity.as_dict() == {
        "anon_session": "session-a",
        "provider_lane": "llm",
        "route_or_model": "gpt-test",
        "call_ordinal": 2,
        "retry_attempt": 1,
        "parent_event_anon": "event-a",
    }
    assert len(identity.key()) == 64


def test_fingerprint_is_canonical_and_never_contains_sensitive_values() -> None:
    first = {"model": "a", "authorization": "Bearer secret", "body": "hello jane@example.com"}
    second = {"body": "hello jane@example.com", "model": "a", "authorization": "another"}
    assert RequestFingerprint.from_request(first) == RequestFingerprint.from_request(second)
    safe = redact_value({"url": "https://x.test/a?sig=topsecret", "phone": "+1 212 555 0110"})
    assert "topsecret" not in str(safe) and "555 0110" not in str(safe)


def test_manifest_has_references_hashes_outcomes_and_invariants() -> None:
    identity = CassetteIdentity("s", "stt", "model", 0, 0, "e")
    case = PackCase(
        "synthetic-1",
        "inputs/synthetic-1.json",
        ("cassettes/a.json",),
        {"status": "ok"},
        ("finalizes",),
        identity,
        RequestFingerprint.from_request({"x": 1}),
    )
    manifest = build_manifest(
        pack_id="local-pack", cases=(case,), artifact_hashes={"inputs/synthetic-1.json": "a" * 64}
    )
    assert manifest["cases"][0]["invariant_ids"] == ["finalizes"]
    assert manifest["artifact_hashes"]["inputs/synthetic-1.json"] == "a" * 64


def test_capture_whitelist_is_default_deny_and_dev_only() -> None:
    config = CaptureWhitelist.from_environ(
        {"OMI_ENV_STAGE": "dev", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    )
    assert config.allows("u1") and not config.allows("u2")
    assert not CaptureWhitelist.from_environ(
        {"OMI_ENV_STAGE": "prod", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    ).allows("u1")
    assert not CaptureWhitelist.from_environ({}).allows("u1")


def test_capture_whitelist_ignores_non_canonical_env_var() -> None:
    """OMI_ENV is not the canonical runtime-stage variable; only OMI_ENV_STAGE gates dev capture."""
    config = CaptureWhitelist.from_environ(
        {"OMI_ENV": "dev", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    )
    assert not config.allows("u1")


def test_redaction_catches_camelcase_credential_keys() -> None:
    """camelCase credential keys like accessToken/clientSecret must be redacted."""
    raw = {"accessToken": "Bearer abc123", "clientSecret": "shh", "model": "gpt-test"}
    safe = redact_value(raw)
    assert safe["accessToken"] == "[REDACTED]"
    assert safe["clientSecret"] == "[REDACTED]"
    assert safe["model"] == "gpt-test"
    # drop_sensitive path (fingerprints) must also catch camelCase
    dropped = redact_value(raw, drop_sensitive=True)
    assert "accessToken" not in dropped
    assert "clientSecret" not in dropped


def test_redaction_catches_plural_and_synonym_credential_keys() -> None:
    """Plurals (cookies/tokens/passwords) and synonyms (passwd/private_key/access_key/bearer/jwt) redact."""
    raw = {
        "cookies": "session=abc",
        "accessTokens": ["t1"],
        "passwords": "p",
        "passwd": "p",
        "private_key": "-----BEGIN-----",
        "access_key": "AKIA...",
        "credentials": "blob",
        "bearer": "xyz",
        "jwt": "eyJ...",
        "model": "gpt-test",
    }
    masked = redact_value(raw)
    for key, original in raw.items():
        if key == "model":
            assert masked[key] == original
        else:
            assert masked[key] == "[REDACTED]", key
    dropped = redact_value(raw, drop_sensitive=True)
    assert dropped["model"] == "gpt-test"
    for key in raw:
        if key != "model":
            assert key not in dropped, key


def test_identity_rejects_whitespace_only_fields() -> None:
    with pytest.raises(ValueError):
        CassetteIdentity("   ", "llm", "model", 0, 0, "event")
    with pytest.raises(ValueError):
        CassetteIdentity("session", "llm", "model", 0, 0, "")


def test_hermetic_runner_denies_egress_counts_fakes_and_runs_cleanup() -> None:
    cleanup: list[str] = []
    with pytest.raises(UnexpectedEgress), hermetic_run(
        cleanup=(lambda: cleanup.append("first"), lambda: cleanup.append("second"))
    ) as fakes:
        fakes.hit("llm")
        fakes.hit("llm")
        fakes.require(llm=2)
        socket.create_connection(("example.com", 443))
    assert cleanup == ["second", "first"]


def test_hermetic_runner_denies_low_level_socket_connect() -> None:
    """The egress-deny guard must block socket.connect, not just create_connection."""
    with pytest.raises(UnexpectedEgress), hermetic_run():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("example.com", 443))


def test_hermetic_runner_denies_dns_resolution() -> None:
    """The egress-deny guard must block DNS resolution."""
    with pytest.raises(UnexpectedEgress), hermetic_run():
        socket.getaddrinfo("example.com", 443)


def test_capture_tap_gates_before_persistence_and_records_wire_events(tmp_path: Path) -> None:
    identity = CassetteIdentity("anon-capture", "stt", "parakeet", 0, 0, "anon-event")
    denied = CaptureTap(tmp_path, CaptureWhitelist.from_environ({}))
    assert denied.start("u1", identity, {"audio": "not-written"}) is None
    assert not (tmp_path / "cassettes").exists()
    assert denied.denied_metadata == [{"provider_lane": "stt", "reason": "whitelist_miss"}]

    ticks = iter((1.0, 1.025, 1.070, 1.100))
    allowed = CaptureWhitelist.from_environ(
        {"OMI_ENV_STAGE": "dev", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    )
    tap = CaptureTap(tmp_path, allowed, clock=lambda: next(ticks))
    invocation = tap.start("u1", identity, {"token": "secret", "audio": "synthetic"})
    assert invocation is not None
    invocation.observe("client", {"type": "audio", "bytes": 4})
    invocation.observe("outbound", {"type": "stt_send"})
    invocation.observe("inbound", {"type": "transcript", "text": "synthetic"})
    cassette = invocation.persist()
    topology = InvocationTopology((cassette,))
    seen = []
    STTCassettePlayer(topology).play(identity, {"audio": "synthetic", "token": "different"}, seen.append)
    assert [(event.direction, event.dt_ms) for event in seen] == [("client", 25), ("outbound", 70), ("inbound", 100)]
    topology.assert_complete()


def test_players_fail_on_extra_out_of_order_and_unused_cassettes(tmp_path: Path) -> None:
    whitelist = CaptureWhitelist.from_environ(
        {"OMI_ENV_STAGE": "dev", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    )
    stt = CassetteIdentity("s", "stt", "model", 0, 0, "e")
    llm = CassetteIdentity("s", "llm", "model", 1, 0, "e")
    tap = CaptureTap(tmp_path, whitelist)
    stt_invocation = tap.start("u1", stt, {"x": 1})
    llm_invocation = tap.start("u1", llm, {"x": 2})
    assert stt_invocation is not None and llm_invocation is not None
    topology = InvocationTopology((stt_invocation.persist(), llm_invocation.persist()))
    with pytest.raises(CassetteTopologyError, match="out-of-order"):
        LLMCassettePlayer(topology).play(llm, {"x": 2}, lambda _: None)
    with pytest.raises(CassetteTopologyError, match="unused"):
        topology.assert_complete()
    STTCassettePlayer(topology).play(stt, {"x": 1}, lambda _: None)
    LLMCassettePlayer(topology).play(llm, {"x": 2}, lambda _: None)
    with pytest.raises(CassetteTopologyError, match="extra"):
        STTCassettePlayer(topology).play(stt, {"x": 1}, lambda _: None)
