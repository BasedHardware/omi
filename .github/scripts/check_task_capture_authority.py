#!/usr/bin/env python3
"""INV-TASK-2 guard: automatic task capture proposes, it never writes a task.

Four structural facts, each the shape of a defect that actually shipped:

1. No capture-policy outcome may mean "create a task now". The policy used to
   return ``auto_accept_silent`` / ``create_direct``, and the adapter turned
   both into create-then-accept in one request.
2. The conversation adapter may not accept a Candidate. Acceptance is the
   user's gesture.
3. ``_save_action_items`` may not call an action-item writer. A fallback there
   wrote a whole conversation's items straight into the task list.
4. The desktop screen-capture client may not expose an ``accept`` at all — a
   delivery path that can accept will eventually be wired to.

Plus a manifest fact: a task source governed by the shared capture policy must
declare no action-item *create* anchor, so a new extraction writer cannot be
registered without failing this guard.

Stdlib-only, no network. Wired from .github/checks-manifest.yaml.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CAPTURE_POLICY = ROOT / "backend/utils/task_intelligence/capture_policy.py"
CONVERSATION_CAPTURE = ROOT / "backend/utils/task_intelligence/conversation_capture.py"
PROCESS_CONVERSATION = ROOT / "backend/utils/conversations/process_conversation.py"
SCREEN_ADAPTER = ROOT / "desktop/macos/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/ScreenCandidateAdapter.swift"
SOURCES_MANIFEST = ROOT / "backend/config/task_intelligence_sources_v1.json"

# Matches the construction, not the word: the files legitimately name these
# outcomes in comments explaining why they no longer exist.
FORBIDDEN_PY_OUTCOME = re.compile(r"""CapturePolicyResult\(\s*['"](auto_accept_silent|create_direct)['"]""")
FORBIDDEN_SWIFT_OUTCOME = re.compile(r"return\s+\.(autoAcceptSilent|createDirect)\b")
ACCEPT_CALL = re.compile(r"candidate_service\.accept_candidate\s*\(")
WRITER_CALL = re.compile(r"action_items_db\.create_action_items?(?:_batch)?\s*\(")
SWIFT_ACCEPT_DECL = re.compile(r"^\s*func\s+accept\s*\(", re.MULTILINE)
CAPTURE_POLICY_CLASS = "shared_capture_policy"
CREATE_SYMBOLS = ("action_items_db.create_action_item", "action_items_db.create_action_items_batch")


def _read(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"missing required source: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8")


def _save_action_items_body(text: str) -> str:
    """Return the body of _save_action_items, or '' when absent."""
    start = text.find("def _save_action_items(")
    if start == -1:
        return ""
    nxt = re.search(r"\n(?=(?:def |@|# ))", text[start + 1 :])
    return text[start : start + 1 + nxt.start()] if nxt else text[start:]


def _client_protocol_body(text: str) -> str:
    """Return the CanonicalScreenCandidateClient protocol body, or '' when absent."""
    match = re.search(r"protocol\s+CanonicalScreenCandidateClient[^{]*\{", text)
    if not match:
        return ""
    depth, i = 1, match.end()
    while i < len(text) and depth:
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return text[match.end() : i - 1]


def main() -> int:
    failures: list[str] = []

    policy = _read(CAPTURE_POLICY, failures)
    for hit in FORBIDDEN_PY_OUTCOME.finditer(policy):
        failures.append(
            f"capture_policy.py returns '{hit.group(1)}'. INV-TASK-2: no capture outcome "
            f"may create a task; return 'pending_candidate' or 'ignore'."
        )

    capture = _read(CONVERSATION_CAPTURE, failures)
    if ACCEPT_CALL.search(capture):
        failures.append(
            "conversation_capture.py calls accept_candidate. INV-TASK-2: extraction proposes; "
            "only an explicit user gesture accepts."
        )

    body = _save_action_items_body(_read(PROCESS_CONVERSATION, failures))
    if WRITER_CALL.search(body):
        failures.append(
            "_save_action_items calls an action-item writer. INV-TASK-2: conversation extraction "
            "writes Candidates only."
        )

    swift = _read(SCREEN_ADAPTER, failures)
    for hit in FORBIDDEN_SWIFT_OUTCOME.finditer(swift):
        failures.append(
            f"ScreenCandidateAdapter returns .{hit.group(1)}. INV-TASK-2: the screen policy must "
            f"stay in parity with the backend and may not create a task."
        )
    if SWIFT_ACCEPT_DECL.search(_client_protocol_body(swift)):
        failures.append(
            "CanonicalScreenCandidateClient declares accept(). INV-TASK-2: the capture pipeline "
            "must have no acceptance path."
        )

    manifest_text = _read(SOURCES_MANIFEST, failures)
    if manifest_text:
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError as exc:
            failures.append(f"task_intelligence_sources_v1.json is not valid JSON: {exc}")
            manifest = {"sources": []}
        for source in manifest.get("sources", []):
            if source.get("policy_class") != CAPTURE_POLICY_CLASS:
                continue
            for anchor in source.get("writer_anchors") or []:
                if anchor.get("symbol") in CREATE_SYMBOLS:
                    failures.append(
                        f"source '{source.get('id')}' is governed by {CAPTURE_POLICY_CLASS} but declares "
                        f"the create anchor '{anchor.get('symbol')}' at {anchor.get('path')}. "
                        f"INV-TASK-2: an automatic capture source may not write action items."
                    )

    if failures:
        print("FAIL: INV-TASK-2 task-capture authority")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("check_task_capture_authority: INV-TASK-2 holds (automatic capture proposes only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
