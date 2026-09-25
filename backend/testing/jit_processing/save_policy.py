"""Small, hermetic oracle for intended JIT memory-save decisions.

This is deliberately not production policy and does not call a model.  It gives
the JIT rollout a stable fixture oracle while the client/backend integration is
still being built.  The evaluator consumes only a candidate, its provenance,
and an optional local fact snapshot; fixture expectations are compared by the
unit test, never consulted while deciding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

_DURABLE_KINDS = frozenset({"durable_correction", "durable_preference", "expensive_conclusion"})
_TASK_KINDS = frozenset({"task", "reminder", "todo"})
_MOOD_KINDS = frozenset({"mood", "ephemeral_state"})

_SECRET_RE = re.compile(
    r"\b(?:api[_ -]?key|access[_ -]?token|password|passcode|secret|private key|recovery code|seed phrase)\b"
    r"|\b(?:sk|pk|ghp|github_pat|xox[baprs]-|AIza)[-_A-Za-z0-9]{10,}\b",
    re.IGNORECASE,
)
_TASK_LANGUAGE_RE = re.compile(
    r"\b(?:remind me|todo|to-do|follow up|follow-up|need to|remember to|send an email|schedule)\b",
    re.IGNORECASE,
)
_MOOD_LANGUAGE_RE = re.compile(
    r"\b(?:i feel|i'm feeling|i am feeling|my mood|feeling stressed|feeling happy|feeling sad|feeling tired)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class JITSaveDecision:
    """The deterministic decision and the candidate metadata it carries."""

    accepted: bool
    reason: str
    kind: str
    slot: str
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _required_text(candidate: Mapping[str, Any], field: str) -> str:
    value = candidate.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"candidate.{field} must be a non-empty string")
    return value.strip()


def _candidate_metadata(candidate: Mapping[str, Any]) -> tuple[str, str, dict[str, Any], str]:
    content = _required_text(candidate, "content")
    kind = _required_text(candidate, "kind")
    slot = _required_text(candidate, "slot")
    provenance = candidate.get("provenance")
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError("candidate.provenance must be a non-empty object")
    subject = candidate.get("subject", "user")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("candidate.subject must be a non-empty string")
    return content, kind, dict(provenance), subject.strip().casefold()


def evaluate_save_candidate(candidate: Mapping[str, Any], *, existing_facts: Sequence[str] = ()) -> JITSaveDecision:
    """Evaluate one intended save without consulting its expected fixture result.

    Rejection is fail-closed for secrets, third-party subjects, task/mood
    material, restatements, unsupported kinds, and malformed metadata.  Accepted
    decisions retain the exact kind, slot, and provenance supplied by the
    candidate so later integration layers can join the write to its source.
    """

    content, kind, provenance, subject = _candidate_metadata(candidate)
    content_key = _normalized(content)
    kind_key = kind.casefold()

    if _SECRET_RE.search(content):
        reason = "secret"
        accepted = False
    elif subject != "user":
        reason = "third_party"
        accepted = False
    elif kind_key in _TASK_KINDS or _TASK_LANGUAGE_RE.search(content):
        reason = "task"
        accepted = False
    elif kind_key in _MOOD_KINDS or _MOOD_LANGUAGE_RE.search(content):
        reason = "mood"
        accepted = False
    elif any(isinstance(fact, str) and _normalized(fact) == content_key for fact in existing_facts):
        reason = "restatement"
        accepted = False
    elif kind_key not in _DURABLE_KINDS:
        reason = "unsupported_kind"
        accepted = False
    else:
        reason = "durable_user_knowledge"
        accepted = True

    return JITSaveDecision(
        accepted=accepted,
        reason=reason,
        kind=kind,
        slot=_required_text(candidate, "slot"),
        provenance=provenance,
    )


def evaluate_fixture_case(case: Mapping[str, Any]) -> JITSaveDecision:
    """Evaluate a JSON fixture case, keeping fixture expectations out of policy."""

    candidate = case.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("case.candidate must be an object")
    user_text = case.get("user_text")
    if not isinstance(user_text, str) or not user_text.strip():
        raise ValueError("case.user_text must be a non-empty string")
    # The user turn is represented in the candidate content for this compact
    # oracle; retaining it in the fixture makes provenance and intent reviewable.
    return evaluate_save_candidate(candidate, existing_facts=case.get("existing_facts", ()))


def load_fixture_cases(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the synthetic cases shipped with this evaluator."""

    fixture_path = path or Path(__file__).with_name("fixtures") / "save_decisions.json"
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("JIT save fixture must be a non-empty list")
    if not all(isinstance(case, dict) for case in raw):
        raise ValueError("JIT save fixture cases must be objects")
    return raw
