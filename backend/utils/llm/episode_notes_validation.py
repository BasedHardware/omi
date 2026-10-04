"""Bounded episode repair that preserves usable notes when the contract fails."""

import json
import re
from typing import Any, Sequence

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from models.structured import NoteClaim, Structured  # type: ignore[reportAttributeAccessIssue]  # Runtime SDK/fallback export.
from utils.conversations.episode_evidence import EvidenceItem, SourceKind, claim_violations
from utils.conversations.episode_vacuity import is_vacuous_note
from utils.llm.meeting_notes_presentation import has_note_content
from utils.llm.meeting_notes_validation import visible_text_fields, enforce_structured_presentation_contract
from utils.observability.fallback import record_fallback

_EPISODE_ID = re.compile(r'(?<![\w-])(?:' + '|'.join(SourceKind.__args__) + r'):[\w:.-]+(?![\w-])')


def sanitize_episode_ids(structured: Structured) -> set[str]:
    violations = set()
    for owner, attribute in visible_text_fields(structured):
        text = getattr(owner, attribute, '') or ''
        if _EPISODE_ID.search(text):
            violations.add('evidence_id_in_prose')
            text = _EPISODE_ID.sub('', text)
            text = re.sub(r'\[\s*\]|\(\s*\)|`\s*`', '', text)
            setattr(owner, attribute, re.sub(r'[ \t]{2,}', ' ', text).strip())
    return violations


def parse_episode_response(raw_response: str, parser: Any) -> tuple[Structured, set[str]]:
    """Bad optional claim annotations cannot invalidate otherwise usable prose."""
    try:
        return parser.parse(raw_response).to_structured(), set()
    except Exception:
        # Preserve the normal parser's Markdown/partial-JSON behavior first.
        # Only salvage schema-invalid annotations from an otherwise complete JSON note.
        text = raw_response.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
        data = json.loads(text)
    violations = set()
    if isinstance(data, dict) and 'note_claims' in data:
        entries = data['note_claims']
        if not isinstance(entries, list):
            violations.add('invalid_claim_schema')
            entries = []
        valid = []
        for entry in entries:
            try:
                valid.append(NoteClaim.model_validate(entry).model_dump(mode='json'))
            except ValidationError:
                violations.add('invalid_claim_schema')
        data['note_claims'] = valid
    return parser.parse(json.dumps(data)).to_structured(), violations


def repair_episode_note(
    structured: Structured,
    *,
    evidence: Sequence[EvidenceItem],
    model: Any,
    messages: Sequence[Any],
    parser: Any,
    raw_response: str,
    content_str: Any,
    transcript_segment_ids: Sequence[str],
    initial_violations: set[str],
) -> Structured:
    violations = initial_violations | sanitize_episode_ids(structured) | claim_violations(structured, evidence)
    if is_vacuous_note(structured):
        violations.add('vacuity')
    if not violations:
        return structured
    try:
        retry = model.invoke(
            [
                *messages,
                HumanMessage(
                    content=(
                        'Regenerate complete JSON once. State concretely what evidence shows and what coverage is missing; '
                        'remove vacuous filler. Repair every claim span, evidence reference and provenance. '
                        'Keep evidence IDs out of visible prose. Errors: '
                        + ', '.join(sorted(violations))
                        + '\nPrior JSON:\n'
                        + raw_response
                    )
                ),
            ]
        )
        # Prefer the retry whenever its extraction schema is structurally valid.
        revised, retry_violations = parse_episode_response(content_str(retry), parser)
        violations |= retry_violations | sanitize_episode_ids(revised)
        if has_note_content(structured) and not has_note_content(revised):
            violations.add('empty_retry')
        else:
            structured = revised
    except Exception:
        violations.add('retry_unavailable')
    residual = sanitize_episode_ids(structured)
    enforce_structured_presentation_contract(structured, transcript_segment_ids, safe_fallback=True)
    residual |= claim_violations(structured, evidence, drop_invalid=True)
    if is_vacuous_note(structured):
        residual.add('vacuity')
    for violation in sorted(violations | residual):
        # Fixed validator classes only; no note text or source contents in telemetry.
        record_fallback(
            component='conversation_notes',
            from_mode='episode_contract',
            to_mode=violation,
            reason='local_heal',
            outcome='degraded' if residual or violations & {'retry_unavailable', 'empty_retry'} else 'recovered',
        )
    return structured
