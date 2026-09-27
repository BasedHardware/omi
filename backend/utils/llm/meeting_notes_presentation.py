"""Bounded repair orchestration for generated conversation-note presentation."""

import logging
from typing import Any, Callable, Iterable, Optional

from langchain_core.messages import SystemMessage

from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
from utils.llm.meeting_notes_validation import (
    PRESENTATION_CONTRACT_VERSION,
    enforce_structured_presentation_contract,
)

logger = logging.getLogger(__name__)


def _response_text(response: Any) -> str:
    content = response.content
    return content if isinstance(content, str) else str(content)


def _record_contract(*, outcome: str, reasons: Iterable[str]) -> None:
    try:
        from utils.metrics import OMI_CONVERSATION_NOTE_PRESENTATION_TOTAL
    except ImportError:  # pragma: no cover - isolated import harness only
        return
    for reason in reasons:
        OMI_CONVERSATION_NOTE_PRESENTATION_TOTAL.labels(
            outcome=outcome, reason=reason, contract_version=PRESENTATION_CONTRACT_VERSION
        ).inc()


def _record_fallback(*, reason: str) -> None:
    try:
        from utils.observability.fallback import record_fallback
    except ImportError:  # pragma: no cover - isolated import harness only
        return
    record_fallback(
        component='conversation_notes',
        from_mode='model_revision',
        to_mode='sanitized_first_response',
        reason=reason,
        outcome='degraded',
        log=logger,
    )


def _has_content(structured: Structured) -> bool:
    return bool(
        structured.title.strip()
        or structured.overview.strip()
        or structured.sections
        or structured.action_items
        or structured.events
    )


def enforce_conversation_note_presentation(
    structured: Structured,
    *,
    raw_response: str,
    model: Any,
    messages: list[Any],
    extraction_parser: Any,
    transcript_segment_ids: Optional[Iterable[object]],
    post_parse_validator: Optional[Callable[[Structured], None]] = None,
) -> Structured:
    """Apply static repair, one targeted revision, then a sanitized fallback."""

    report = enforce_structured_presentation_contract(structured, transcript_segment_ids)
    outcome = 'passed'
    if report.needs_revision:
        revision_messages = [
            *messages,
            SystemMessage(
                content='The prior JSON exposed an internal source_segment_id in user-visible prose. '
                'Regenerate the complete JSON once. Put exact transcript IDs only in source_segment_ids arrays; '
                'do not place them in titles, headings, Markdown bodies, links, actions, events, participants, or insights. '
                f'Prior JSON:\n{raw_response}'
            ),
        ]
        try:
            revised_response = extraction_parser.parse(_response_text(model.invoke(revision_messages)))
            revised_structured = revised_response.to_structured()
            if _has_content(structured) and not _has_content(revised_structured):
                raise ValueError('presentation revision returned an empty note')
            structured = revised_structured
            if post_parse_validator:
                post_parse_validator(structured)
            report = enforce_structured_presentation_contract(structured, transcript_segment_ids)
            if report.needs_revision:
                report = enforce_structured_presentation_contract(
                    structured, transcript_segment_ids, safe_fallback=True
                )
                outcome = 'safe_fallback'
                _record_fallback(reason='policy')
            else:
                outcome = 'revision_repair'
        except Exception:
            report = enforce_structured_presentation_contract(structured, transcript_segment_ids, safe_fallback=True)
            outcome = 'safe_fallback'
            report.repairs.add('revision_error')
            _record_fallback(reason='other')
    elif report.repairs:
        outcome = 'static_repair'

    _record_contract(outcome=outcome, reasons=sorted(report.repairs | report.violations) or ['ok'])
    return structured
