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


def test_ambiguous_codemagic_retry_can_only_claim_one_qualification_run() -> None:
    pending, changed = dispatch.initialize(
        candidate_body(), key=KEY, updated_at=NOW, diagnostic="candidate published; dispatch requested"
    )
    assert changed
    queued, changed = dispatch.mark(
        pending,
        state="queued",
        key=KEY,
        attempt=1,
        updated_at=NOW,
        diagnostic="GitHub Actions dispatch accepted",
    )
    assert changed
    running, should_run, reason = dispatch.claim(
        queued,
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
    pending, _ = dispatch.initialize(candidate_body(), key=KEY, updated_at=NOW, diagnostic="candidate published")
    running, should_run, _ = dispatch.claim(
        pending,
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


def test_ambiguous_timeout_failure_still_allows_its_same_key_to_claim_once() -> None:
    pending, _ = dispatch.initialize(candidate_body(), key=KEY, updated_at=NOW, diagnostic="candidate published")
    unknown, changed = dispatch.mark(
        pending,
        state="dispatch_failed",
        key=KEY,
        attempt=3,
        updated_at=NOW,
        diagnostic="GitHub Actions dispatch was not confirmed after 3 attempts; candidate remains non-live",
    )
    assert changed

    running, should_run, reason = dispatch.claim(
        unknown,
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


def test_dispatch_status_cannot_modify_factual_qualification_evidence() -> None:
    body = candidate_body()
    pending, _ = dispatch.initialize(body, key=KEY, updated_at=NOW, diagnostic="candidate published")
    running, should_run, _ = dispatch.claim(
        pending,
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


def test_invalid_dispatch_diagnostic_is_rejected() -> None:
    try:
        dispatch.initialize(candidate_body(), key=KEY, updated_at=NOW, diagnostic="first line\nsecond line")
    except SystemExit as exc:
        assert "single-line" in str(exc)
    else:
        raise AssertionError("newline diagnostic should fail closed")


if __name__ == "__main__":
    test_ambiguous_codemagic_retry_can_only_claim_one_qualification_run()
    test_terminal_failure_requires_an_explicit_new_retry_nonce()
    test_ambiguous_timeout_failure_still_allows_its_same_key_to_claim_once()
    test_dispatch_status_cannot_modify_factual_qualification_evidence()
    test_invalid_dispatch_diagnostic_is_rejected()
    print("desktop qualification dispatch tests OK")
