#!/usr/bin/env python3
"""Validate and map the privacy-safe context-bucket director benchmark.

This is an offline contract gate. It does not call a model or read local user
data; it proves every director-owned fixture maps to the DEBUG probe ABI and
keeps lifecycle-only cases explicitly separated.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib import error, request


DIRECTOR_CASES = {
    "worthy-urgent-commitment",
    "worthy-specific-context-change",
    "worthy-revisit-unresolved-task",
    "worthy-new-actionable-fact",
    "silence-ambient-narrative",
    "silence-low-confidence-fact",
    "identity-same-numbered-context",
    "identity-similar-title-isolated",
    "identity-workstream-split",
    "freshness-new-identifier",
    "privacy-injected-bucket-text",
    "privacy-sensitive-frame-not-evidence",
    "commitment-explicit-due-date",
    "commitment-ambiguous-mention",
}


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
    tasks = [
        {"description": task["description"], "due_at": task.get("dueAt")}
        for task in synthetic.get("tasks", [])
        if task.get("status") == "open"
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
        raise RuntimeError(f"{case['id']}: probe returned HTTP {exc.code}") from exc
    if envelope.get("ok") is not True:
        raise RuntimeError(f"{case['id']}: probe failed: {envelope.get('error', 'unknown error')}")
    result = envelope.get("result", envelope)
    detail = result.get("detail", result)
    decision = detail.get("decision")
    polarity = "silence" if decision == "silence" else "notify"
    expected = case["expectedAction"]
    result = {
        "id": case["id"],
        "expectedAction": expected,
        "decision": decision,
        "polarity": polarity,
        "matched": expected == "either" or expected == polarity,
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
        print(f"context bucket director replay: {matched}/{len(results)} polarity matches")
        return 0 if matched == len(results) else 1
    print(f"context bucket benchmark contract passed: {total} cases, {director} director mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
