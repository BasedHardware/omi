"""Behavioral tests for the desktop qualification dispatch ownership protocol."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("desktop_qualification_dispatch.py")
SPEC = importlib.util.spec_from_file_location("desktop_qualification_dispatch", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
dispatch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dispatch)

KEY = "codemagic:v0.12.64+12064-macos"
NOW = "2026-07-20T10:00:00Z"


def candidate_body(extra: str = "") -> str:
    return "\n".join(
        [
            "<!-- KEY_VALUE_START",
            "isLive: false",
            "channel: candidate",
            "edSignature: signature",
            "qualifiedBeta: false",
            "qualifiedBetaEvidence: qualification-evidence-failed.json",
            extra,
            "KEY_VALUE_END -->",
        ]
    )


def test_serialized_runner_claims_can_only_start_one_qualification_run() -> None:
    running, should_run, reason = dispatch.claim(
        candidate_body(),
        key=KEY,
        updated_at=NOW,
        run_id="42",
        run_url="https://github.com/BasedHardware/omi/actions/runs/42",
        allow_retry=False,
    )
    assert should_run and reason == "claimed"

    duplicate, should_run, reason = dispatch.claim(
        running,
        key=KEY,
        updated_at=NOW,
        run_id="43",
        run_url="https://github.com/BasedHardware/omi/actions/runs/43",
        allow_retry=False,
    )
    assert duplicate == running
    assert not should_run
    assert reason == "dispatch key already running"


def test_terminal_failure_requires_an_explicit_new_retry_nonce() -> None:
    running, should_run, _ = dispatch.claim(
        candidate_body(),
        key=KEY,
        updated_at=NOW,
        run_id="42",
        run_url="https://github.com/BasedHardware/omi/actions/runs/42",
        allow_retry=False,
    )
    assert should_run
    failed = dispatch.complete(running, key=KEY, updated_at=NOW, passed=False)

    unchanged, should_run, reason = dispatch.claim(
        failed,
        key="manual:v0.12.64+12064-macos:retry-1",
        updated_at=NOW,
        run_id="43",
        run_url="https://github.com/BasedHardware/omi/actions/runs/43",
        allow_retry=False,
    )
    assert unchanged == failed
    assert not should_run
    assert "explicit retry nonce" in reason

    retried, should_run, _ = dispatch.claim(
        failed,
        key="manual:v0.12.64+12064-macos:retry-1",
        updated_at=NOW,
        run_id="43",
        run_url="https://github.com/BasedHardware/omi/actions/runs/43",
        allow_retry=True,
    )
    assert should_run
    assert "qualificationDispatchKey: manual:v0.12.64+12064-macos:retry-1" in retried


def test_legacy_dispatch_failure_still_allows_its_same_key_to_claim_once() -> None:
    dispatch_failed = candidate_body(
        "qualificationDispatchState: dispatch_failed\n"
        f"qualificationDispatchKey: {KEY}\n"
        "qualificationDispatchAttempt: 3\n"
        "qualificationDispatchUpdatedAt: 2026-07-20T09:00:00Z\n"
        "qualificationDispatchDiagnostic: dispatch confirmation timed out"
    )
    running, should_run, reason = dispatch.claim(
        dispatch_failed,
        key=KEY,
        updated_at=NOW,
        run_id="44",
        run_url="https://github.com/BasedHardware/omi/actions/runs/44",
        allow_retry=False,
    )
    assert should_run and reason == "claimed"
    duplicate, should_run, _ = dispatch.claim(
        running,
        key=KEY,
        updated_at=NOW,
        run_id="45",
        run_url="https://github.com/BasedHardware/omi/actions/runs/45",
        allow_retry=False,
    )
    assert duplicate == running
    assert not should_run


def test_expired_running_claim_can_be_recovered_only_after_the_bounded_lease() -> None:
    running, should_run, _ = dispatch.claim(
        candidate_body(),
        key=KEY,
        updated_at=NOW,
        run_id="42",
        run_url="https://github.com/BasedHardware/omi/actions/runs/42",
        allow_retry=False,
    )
    assert should_run

    unchanged, should_run, reason = dispatch.claim(
        running,
        key=KEY,
        updated_at="2026-07-20T11:59:59Z",
        run_id="43",
        run_url="https://github.com/BasedHardware/omi/actions/runs/43",
        allow_retry=False,
    )
    assert unchanged == running
    assert not should_run
    assert reason == "dispatch key already running"

    recovered, should_run, reason = dispatch.claim(
        running,
        key=KEY,
        updated_at="2026-07-20T12:00:00Z",
        run_id="44",
        run_url="https://github.com/BasedHardware/omi/actions/runs/44",
        allow_retry=False,
    )
    assert should_run
    assert reason == "reclaimed stale claim"
    assert "qualificationDispatchAttempt: 2" in recovered
    assert "qualificationDispatchRunId: 44" in recovered


def test_unknown_existing_dispatch_state_is_rejected() -> None:
    body = candidate_body("qualificationDispatchState: abandoned\nqualificationDispatchKey: " + KEY)
    try:
        dispatch.claim(
            body,
            key=KEY,
            updated_at=NOW,
            run_id="42",
            run_url="https://github.com/BasedHardware/omi/actions/runs/42",
            allow_retry=False,
        )
    except SystemExit as exc:
        assert "unknown existing" in str(exc)
    else:
        raise AssertionError("unknown existing dispatch state should fail closed")


def test_expired_claim_from_another_dispatch_key_does_not_block_recovery() -> None:
    running, should_run, _ = dispatch.claim(
        candidate_body(),
        key="manual:v0.12.64+12064-macos:retry-1",
        updated_at="2026-07-20T08:00:00Z",
        run_id="42",
        run_url="https://github.com/BasedHardware/omi/actions/runs/42",
        allow_retry=True,
    )
    assert should_run

    recovered, should_run, reason = dispatch.claim(
        running,
        key=KEY,
        updated_at="2026-07-20T10:00:00Z",
        run_id="43",
        run_url="https://github.com/BasedHardware/omi/actions/runs/43",
        allow_retry=False,
    )
    assert should_run
    assert reason == "reclaimed stale claim"
    assert f"qualificationDispatchKey: {KEY}" in recovered


def test_dispatch_status_cannot_modify_factual_qualification_evidence() -> None:
    body = candidate_body()
    running, should_run, _ = dispatch.claim(
        body,
        key=KEY,
        updated_at=NOW,
        run_id="42",
        run_url="https://github.com/BasedHardware/omi/actions/runs/42",
        allow_retry=False,
    )
    assert should_run
    qualified = dispatch.complete(running, key=KEY, updated_at=NOW, passed=True)

    assert "qualifiedBetaEvidence: qualification-evidence-failed.json" in qualified
    assert "qualificationDispatchState: qualified" in qualified


def test_invalid_existing_running_claim_timestamp_is_rejected() -> None:
    body = candidate_body(
        "qualificationDispatchState: running\n"
        f"qualificationDispatchKey: {KEY}\n"
        "qualificationDispatchAttempt: 1\n"
        "qualificationDispatchUpdatedAt: not-a-timestamp\n"
        "qualificationDispatchDiagnostic: runner claimed this key"
    )
    try:
        dispatch.claim(
            body,
            key=KEY,
            updated_at="2026-07-20T12:00:00Z",
            run_id="43",
            run_url="https://github.com/BasedHardware/omi/actions/runs/43",
            allow_retry=False,
        )
    except SystemExit as exc:
        assert "existing updated_at" in str(exc)
    else:
        raise AssertionError("invalid running claim timestamp should fail closed")


if __name__ == "__main__":
    test_serialized_runner_claims_can_only_start_one_qualification_run()
    test_terminal_failure_requires_an_explicit_new_retry_nonce()
    test_legacy_dispatch_failure_still_allows_its_same_key_to_claim_once()
    test_expired_running_claim_can_be_recovered_only_after_the_bounded_lease()
    test_unknown_existing_dispatch_state_is_rejected()
    test_expired_claim_from_another_dispatch_key_does_not_block_recovery()
    test_dispatch_status_cannot_modify_factual_qualification_evidence()
    test_invalid_existing_running_claim_timestamp_is_rejected()
    print("desktop qualification dispatch tests OK")
