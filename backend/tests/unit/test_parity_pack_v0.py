from __future__ import annotations

import socket

import pytest

from testing.parity_pack_v0.manifest import PackCase, build_manifest
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
        {"OMI_ENV": "dev", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    )
    assert config.allows("u1") and not config.allows("u2")
    assert not CaptureWhitelist.from_environ(
        {"OMI_ENV": "prod", "OMI_PARITY_PACK_CAPTURE": "1", "OMI_PARITY_PACK_ALLOWED_PRINCIPALS": "u1"}
    ).allows("u1")
    assert not CaptureWhitelist.from_environ({}).allows("u1")


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
