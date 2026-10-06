"""Bounded episode repair that preserves usable notes when the contract fails."""

import json
import re
from typing import Any, Sequence

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from models.episode_extraction import ExtractedNoteClaim
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # Runtime SDK/fallback export.
from utils.conversations.episode_evidence import EvidenceItem, SourceKind, claim_violations, restore_episode_claim_ids
from utils.conversations.episode_vacuity import is_vacuous_note
from utils.llm.episode_writer import episode_input_bytes
from utils.llm.meeting_notes_presentation import has_note_content
from utils.llm.meeting_notes_validation import visible_text_fields, enforce_structured_presentation_contract
from utils.observability.fallback import record_fallback

_EPISODE_ID = re.compile(r'(?<![\w-])(?:' + '|'.join((*SourceKind.__args__, 'evidence')) + r'):[\w:.-]+(?![\w-])')


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
                valid.append(ExtractedNoteClaim.model_validate(entry).model_dump(mode='json'))
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
    run: Any = None,
    repair_budget: float = 60,
    retry_model_factory: Any = None,
    claims_enabled: bool = True,
) -> Structured:
    restore_episode_claim_ids(structured.note_claims or [], evidence)
    violations = initial_violations | sanitize_episode_ids(structured)
    presentation = enforce_structured_presentation_contract(structured, transcript_segment_ids)
    if presentation.needs_revision:
        violations.add('presentation_contract')
    if claims_enabled:
        violations |= claim_violations(structured, evidence)
    else:
        structured.note_claims = None
    if is_vacuous_note(structured):
        violations.add('vacuity')
    if not violations:
        return structured
    try:
        # Long inputs get local repair only; never buy a second full long-context call.
        remaining = run.remaining(repair_budget) if run else repair_budget
        if (run and run.repair_disabled) or remaining < 15 or episode_input_bytes(messages) > 120000:
            violations.add('repair_budget_exhausted')
            raise TimeoutError('repair budget exhausted')
        retry_model = retry_model_factory((remaining // 5) * 5) if retry_model_factory is not None else model
        invoke = (lambda payload: run.invoke(retry_model, payload)) if run else retry_model.invoke
        retry = invoke(
            [
                *messages,
                HumanMessage(
                    content=(
                        'Regenerate complete JSON once. State concretely what evidence shows and what coverage is missing; '
                        'remove vacuous filler. '
                        + (
                            'Repair every claim span, evidence reference and provenance. '
                            if claims_enabled
                            else 'Repair source attribution and uncertainty; do not generate note_claims. '
                        )
                        + 'Keep evidence IDs out of visible prose. Errors: '
                        + ', '.join(sorted(violations))
                    )
                ),
            ]
        )
        # Prefer the retry whenever its extraction schema is structurally valid.
        revised, retry_violations = parse_episode_response(content_str(retry), parser)
        restore_episode_claim_ids(revised.note_claims or [], evidence)
        violations |= retry_violations | sanitize_episode_ids(revised)
        if has_note_content(structured) and not has_note_content(revised):
            violations.add('empty_retry')
        else:
            structured = revised
    except Exception:
        violations.add('retry_unavailable')
    residual = sanitize_episode_ids(structured)
    enforce_structured_presentation_contract(structured, transcript_segment_ids, safe_fallback=True)
    if claims_enabled:
        residual |= claim_violations(structured, evidence, drop_invalid=True)
    else:
        structured.note_claims = None
    if is_vacuous_note(structured):
        residual.add('vacuity')
    if run is not None:
        run.violations.update(violations | residual)
        run.vacuity = is_vacuous_note(structured)
        run.fallback_to_best_note = bool(residual or violations & {'retry_unavailable', 'empty_retry'})
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
