#!/usr/bin/env python3
"""Validate and map the privacy-safe context-bucket director benchmark.

This is an offline contract gate. It does not call a model or read local user
data; it proves every director-owned fixture maps to the DEBUG probe ABI and
keeps lifecycle-only cases explicitly separated.

`--invoke` additionally replays the deck through the DEBUG probe on a running
named QA bundle. There it scores referent identifiability: a case may declare
`referentTokens`, the identifying strings its own synthetic context supplies,
and a spoken decision whose title and message contain none of them fails as
`unnamed_referent`. `reasoning` is excluded on purpose -- the user never sees
it, so it cannot be what makes a notification identifiable.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys
from urllib import error, request


DIRECTOR_CASES = {
    "worthy-urgent-commitment",
    "worthy-specific-context-change",
    "worthy-material-change-no-commitment",
    "worthy-revisit-unresolved-task",
    "worthy-new-actionable-fact",
    "silence-ambient-narrative",
    "silence-low-confidence-fact",
    "identity-same-numbered-context",
    "identity-similar-title-isolated",
    "identity-workstream-split",
    "freshness-new-identifier",
    "privacy-injected-bucket-text",
    "privacy-eligible-injection-with-valid-deadline",
    "privacy-sensitive-frame-not-evidence",
    "commitment-explicit-due-date",
    "commitment-ambiguous-mention",
    "referent-pull-request",
    "referent-email-thread",
    "referent-document-comment",
    "referent-person-request",
    "referent-meeting-conflict",
    "referent-file-build-failure",
    "referent-visible-on-screen",
    "referent-no-identifier",
}

# Cases whose point is that a spoken message must name the thing it is about.
# Each declares `referentTokens`: the identifying strings its own synthetic
# context supplies. A notification that contains none of them is unusable —
# the user cannot tell which pull request, which thread, which document.
REFERENT_CASES = {case for case in DIRECTOR_CASES if case.startswith("referent-")}

STABLE_PROACTIVE_ERROR = re.compile(r"\bproactive_(?:http_error status=\d{3}|invalid_response|owner_changed)\b")
DIRECTOR_DECISIONS = {"suggest", "insight", "task_candidate", "resurface", "silence"}


def map_case(case: dict) -> dict[str, str]:
    synthetic = case["synthetic"]
    bucket = synthetic["bucket"]
    entries = bucket.get("entries", [])
    frames = sorted(synthetic.get("frames", []), key=lambda frame: frame["capturedAt"])
    if not frames:
        raise ValueError(f"{case['id']}: director case requires a synthetic frame")
    frame = frames[-1]
    facts = []
    for entry in entries:
        for fact in entry.get("facts", []):
            if fact.get("validityState") != "validated":
                continue
            refs = fact.get("evidenceRefs") or entry.get("evidenceRefs", [])
            evidence = fact.get("evidenceText") or fact["statement"]
            facts.append(
                f"fact:{fact['id']} {fact['statement']} "
                f"[evidence: {evidence}; refs: {json.dumps(refs, separators=(',', ':'))}]"
            )
    evaluation_time = datetime.fromisoformat(frame["capturedAt"].replace("Z", "+00:00"))
    task_cutoff = evaluation_time + timedelta(hours=48)
    tasks = sorted(
        [task for task in synthetic.get("tasks", []) if task.get("status") == "open"],
        key=lambda task: (
            bool(
                task.get("dueAt")
                and datetime.fromisoformat(task["dueAt"].replace("Z", "+00:00")) > task_cutoff
            ),
            datetime.fromisoformat(task["dueAt"].replace("Z", "+00:00"))
            if task.get("dueAt")
            else datetime.max.replace(tzinfo=evaluation_time.tzinfo),
            task.get("id", ""),
        ),
    )[:20]
    tasks = [
        {"description": task["description"], "due_at": task.get("dueAt")}
        for task in tasks
    ]
    return {
        "bucket_id": bucket["id"],
        "version": str(bucket["version"]),
        "header": f"Persistent work context; {len(entries)} qualifying visits.",
        "frozen": "[]",
        "tail": json.dumps(
            [f"entry:{entry['id']} {entry['narrative']}" for entry in entries[-5:]],
            separators=(",", ":"),
        ),
        "validated_facts": json.dumps(facts, separators=(",", ":")),
        "tasks": json.dumps(tasks, separators=(",", ":")),
        "app": frame["appName"],
        "window": frame["windowTitle"],
        "captured_at": frame["capturedAt"],
        "notify_worthiness": str(bucket.get("notifyWorthiness", 0)),
    }


def validate(deck: dict) -> tuple[int, int]:
    if deck.get("version") != 1 or deck.get("privacyContract", {}).get("syntheticOnly") is not True:
        raise ValueError("benchmark must be v1 and synthetic-only")
    if deck["privacyContract"].get("rawImageBytesIncluded") is not False:
        raise ValueError("director benchmark must remain image-independent")
    if deck["privacyContract"].get("directorReplayScope") != "image_independent":
        raise ValueError("director replay must explicitly declare its image-independent scope")
    cases = deck.get("cases", [])
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)) or set(ids) != {case["id"] for case in cases}:
        raise ValueError("case IDs must be present and unique")
    if not DIRECTOR_CASES.issubset(set(ids)):
        raise ValueError("director case registry drifted from fixture")
    for case in cases:
        if case.get("expectedAction") not in {"notify", "silence", "either"}:
            raise ValueError(f"{case['id']}: invalid expectedAction")
        if not isinstance(case.get("forbidden"), list) or not case["forbidden"]:
            raise ValueError(f"{case['id']}: forbidden behavior contract is required")
        forbidden_output_terms = case.get("forbiddenOutputTerms", [])
        if not isinstance(forbidden_output_terms, list) or any(
            not isinstance(term, str) or not term.strip() for term in forbidden_output_terms
        ):
            raise ValueError(f"{case['id']}: forbiddenOutputTerms must be non-empty strings")
        allowed_decisions = case.get("allowedDecisions", [])
        if not isinstance(allowed_decisions, list) or any(
            decision not in DIRECTOR_DECISIONS for decision in allowed_decisions
        ):
            raise ValueError(f"{case['id']}: allowedDecisions must use director decision values")
        referent_tokens = case.get("referentTokens", [])
        if not isinstance(referent_tokens, list) or any(
            not isinstance(token, str) or not token.strip() for token in referent_tokens
        ):
            raise ValueError(f"{case['id']}: referentTokens must be non-empty strings")
        # `referent-no-identifier` is the deliberate exception: its whole point is
        # that its context supplies no handle, so nothing may be named and nothing
        # may be invented.
        if case["id"] in REFERENT_CASES and not referent_tokens and case["id"] != "referent-no-identifier":
            raise ValueError(f"{case['id']}: referent cases must declare referentTokens")
        if case["id"] in DIRECTOR_CASES:
            params = map_case(case)
            required = {
                "bucket_id", "version", "header", "frozen", "tail", "validated_facts",
                "tasks", "app", "window", "captured_at", "notify_worthiness",
            }
            if set(params) != required:
                raise ValueError(f"{case['id']}: probe ABI mapping drift")
    return len(cases), len(DIRECTOR_CASES)


def invoke_case(case: dict, port: int, include_text: bool = False) -> dict:
    """Invoke the no-delivery DEBUG probe against a local named QA bundle."""
    scripts_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts_dir))
    from automation_token_lib import automation_token  # pylint: disable=import-outside-toplevel

    token = os.environ.get("OMI_AUTOMATION_TOKEN") or automation_token(port)
    if not token:
        raise RuntimeError(f"automation token unavailable for port {port}")
    body = json.dumps(
        {"name": "probe_context_bucket_director", "params": map_case(case)},
        separators=(",", ":"),
    ).encode()
    bridge_request = request.Request(
        f"http://127.0.0.1:{port}/action",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(bridge_request, timeout=45) as response:
            envelope = json.load(response)
    except error.HTTPError as exc:
        stable_error = None
        try:
            error_envelope = json.loads(exc.read(4096))
            match = STABLE_PROACTIVE_ERROR.search(str(error_envelope.get("error", "")))
            stable_error = match.group(0) if match else None
        except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
            pass
        suffix = f" ({stable_error})" if stable_error else ""
        raise RuntimeError(f"{case['id']}: probe returned HTTP {exc.code}{suffix}") from exc
    if envelope.get("ok") is not True:
        raise RuntimeError(f"{case['id']}: probe failed: {envelope.get('error', 'unknown error')}")
    result = envelope.get("result", envelope)
    detail = result.get("detail", result)
    decision = detail.get("decision")
    if decision not in DIRECTOR_DECISIONS:
        raise RuntimeError(f"{case['id']}: probe returned invalid decision")
    polarity = "silence" if decision == "silence" else "notify"
    expected = case["expectedAction"]
    response_text = "\n".join(
        str(detail.get(field) or "") for field in ("title", "message", "reasoning")
    ).casefold()
    forbidden_output_terms = case.get("forbiddenOutputTerms", [])
    forbidden_terms_matched = [
        term for term in forbidden_output_terms if term.casefold() in response_text
    ]
    # The user-visible surface is title + message; `reasoning` never reaches the
    # user, so it cannot supply the identifying context.
    visible_text = "\n".join(str(detail.get(field) or "") for field in ("title", "message")).casefold()
    referent_tokens = case.get("referentTokens", [])
    referent_hits = [token for token in referent_tokens if token.casefold() in visible_text]
    referent_named = bool(referent_hits) if referent_tokens else None
    polarity_matched = expected == "either" or expected == polarity
    allowed_decisions = case.get("allowedDecisions", [])
    decision_matched = not allowed_decisions or decision in allowed_decisions
    failure_reasons = []
    if not polarity_matched:
        failure_reasons.append("polarity")
    if not decision_matched:
        failure_reasons.append("decision")
    if forbidden_terms_matched:
        failure_reasons.append("forbidden_output")
    referent_required = decision != "silence" and bool(referent_tokens)
    if referent_required and not referent_hits:
        failure_reasons.append("unnamed_referent")
    result = {
        "id": case["id"],
        "expectedAction": expected,
        "decision": decision,
        "polarity": polarity,
        "matched": (
            polarity_matched
            and decision_matched
            and not forbidden_terms_matched
            and not (referent_required and not referent_hits)
        ),
        "polarity_matched": polarity_matched,
        "decision_matched": decision_matched,
        "forbidden_output_matched": bool(forbidden_terms_matched),
        "forbidden_terms_matched": forbidden_terms_matched,
        "referent_named": referent_named,
        "referent_hits": referent_hits,
        "failure_reasons": failure_reasons,
        "model": detail.get("model"),
        "latency_ms": detail.get("latency_ms"),
    }
    if include_text:
        result.update(
            title=detail.get("title"),
            message=detail.get("message"),
            reasoning=detail.get("reasoning"),
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixture",
        nargs="?",
        default="desktop/macos/e2e/fixtures/context-bucket-proactivity-benchmark.json",
    )
    parser.add_argument("--emit-probe-params", action="store_true")
    parser.add_argument("--invoke", action="store_true")
    parser.add_argument(
        "--include-text",
        action="store_true",
        help="Include synthetic probe title/message/reasoning in live replay output.",
    )
    parser.add_argument("--port", type=int, default=47910)
    args = parser.parse_args()
    deck = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    total, director = validate(deck)
    director_cases = [case for case in deck["cases"] if case["id"] in DIRECTOR_CASES]
    if args.emit_probe_params:
        print(json.dumps([{"id": case["id"], "params": map_case(case)} for case in director_cases], indent=2))
        return 0
    if args.invoke:
        results = []
        for case in director_cases:
            try:
                results.append(invoke_case(case, args.port, include_text=args.include_text))
            except (RuntimeError, OSError, ValueError) as exc:
                results.append(
                    {
                        "id": case["id"],
                        "expectedAction": case["expectedAction"],
                        "decision": None,
                        "polarity": "error",
                        "matched": False,
                        "error": str(exc),
                    }
                )
        print(json.dumps(results, indent=2))
        matched = sum(result["matched"] for result in results)
        print(f"context bucket director replay: {matched}/{len(results)} behavioral contracts passed")
        return 0 if matched == len(results) else 1
    print(f"context bucket benchmark contract passed: {total} cases, {director} director mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
