"""Independent classification of deterministically detected Omi invocations."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
import json
import logging
from typing import Any, Literal

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from utils.llm.clients import get_llm
from utils.llm.gateway_client import should_route_features_through_gateway
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

WakeWordInvocationVerdictValue = Literal[
    'task_command',
    'memory_command',
    'question',
    'quoted_or_meta',
    'not_addressed_to_omi',
    'abandoned',
    'unclear',
]


class WakeWordInvocationVerdict(BaseModel):
    segment_ids: list[str]
    verdict: WakeWordInvocationVerdictValue
    evidence_quote: str
    payload_segment_ids: list[str] = Field(default_factory=list)


class WakeWordAdjudication(BaseModel):
    invocations: list[WakeWordInvocationVerdict] = Field(default_factory=list)


WAKE_WORD_ADJUDICATION_PROMPT = '''You classify phrases that a deterministic matcher already detected.

This is classification, not intent extraction. Do not draft, rewrite, or infer a task. The separate
action-item extractor has already run and its descriptions are intentionally withheld from you so
that its wording cannot anchor this decision.

Read the entire marked transcript and classify each distinct detected invocation. The
matched_segment_ids input contains segment IDs only; it does not assert that the phrase addresses
Omi or that it is actionable. Speaker labels identify the primary user versus other speakers.

Return one of these discrete verdicts for each invocation:
- task_command: the primary user deliberately addressed Omi with a concrete task/reminder command.
- memory_command: the primary user deliberately addressed Omi with a concrete remember/save command.
- question: the primary user deliberately addressed Omi with a question, not a task command.
- quoted_or_meta: the phrase is quoted, demonstrated, documented, or discussed as a phrase/feature.
- not_addressed_to_omi: it is not this primary user's invocation of Omi, including TV, demo playback,
  bystander speech, or speech directed to another device/person.
- abandoned: the speaker withdrew or abandoned the invocation.
- unclear: context does not support any more specific verdict.

Rejection verdicts are first-class answers. Do not turn a likely phrase into a command merely because
an extracted_item_ref exists. For evidence_quote, copy a short verbatim quote that appears inside one
of that invocation's segment_ids. Use payload_segment_ids only for transcript segments that contain
the command/question payload. Never output an action-item description.

{format_instructions}'''


def _segment_value(segment: Any, field: str, default: Any = None) -> Any:
    if isinstance(segment, Mapping):
        return segment.get(field, default)
    return getattr(segment, field, default)


def _eligible_item_refs(action_items: Sequence[Any], matched_segment_ids: set[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item_index, item in enumerate(action_items):
        source_segment_ids = [
            str(segment_id) for segment_id in (getattr(item, 'source_segment_ids', None) or []) if segment_id
        ]
        if matched_segment_ids.intersection(source_segment_ids):
            refs.append({'item_index': item_index, 'source_segment_ids': source_segment_ids})
    return refs


def validate_wake_word_adjudication(
    adjudication: WakeWordAdjudication,
    *,
    matched_segment_ids: Collection[str],
    transcript_segments: Sequence[Any],
) -> WakeWordAdjudication:
    """Drop model verdicts that escape deterministic IDs or lack verbatim evidence."""

    matched_ids = {str(segment_id) for segment_id in matched_segment_ids}
    text_by_id = {
        str(segment_id): text
        for segment in transcript_segments
        if (segment_id := _segment_value(segment, 'id')) and isinstance((text := _segment_value(segment, 'text')), str)
    }
    all_segment_ids = set(text_by_id)
    valid: list[WakeWordInvocationVerdict] = []
    for invocation in adjudication.invocations:
        invocation_ids = list(dict.fromkeys(invocation.segment_ids))
        invocation_id_set = set(invocation_ids)
        if not invocation_ids or not invocation_id_set.issubset(matched_ids):
            logger.warning('Dropping wake-word verdict with IDs outside the deterministic match set')
            continue
        evidence_quote = invocation.evidence_quote.strip()
        if not evidence_quote or not any(
            evidence_quote in text_by_id.get(segment_id, '') for segment_id in invocation_ids
        ):
            logger.warning('Dropping wake-word verdict whose evidence quote is not verbatim in its matched segments')
            continue
        payload_segment_ids = [
            segment_id for segment_id in dict.fromkeys(invocation.payload_segment_ids) if segment_id in all_segment_ids
        ]
        valid.append(
            invocation.model_copy(
                update={
                    'segment_ids': invocation_ids,
                    'evidence_quote': evidence_quote,
                    'payload_segment_ids': payload_segment_ids,
                }
            )
        )
    return WakeWordAdjudication(invocations=valid)


def adjudicate_wake_word_invocations(
    *,
    marked_transcript: str,
    matched_segment_ids: Collection[str],
    action_items: Sequence[Any],
    speaker_labels: Sequence[Mapping[str, Any]],
    transcript_segments: Sequence[Any],
) -> WakeWordAdjudication:
    """Run the independently framed, extended-reasoning invocation classifier."""

    matched_ids = {str(segment_id) for segment_id in matched_segment_ids if segment_id}
    if not matched_ids:
        return WakeWordAdjudication()

    parser = PydanticOutputParser(pydantic_object=WakeWordAdjudication)
    prompt = ChatPromptTemplate.from_messages(
        [
            ('system', WAKE_WORD_ADJUDICATION_PROMPT),
            ('human', '{payload}'),
        ]
    )
    payload = {
        'full_marked_transcript': marked_transcript,
        'matched_segment_ids': sorted(matched_ids),
        'extracted_item_refs': _eligible_item_refs(action_items, matched_ids),
        'speaker_labels': list(speaker_labels),
    }
    try:
        # This classification boundary is the only wake-word call that receives
        # extended reasoning. Gateway mode owns that option in its route artifact;
        # direct mode binds the equivalent provider request option here.
        reasoning_model = get_llm('wake_word_adjudication')
        if not should_route_features_through_gateway():
            reasoning_model = reasoning_model.bind(reasoning_effort='high')
        raw = (prompt | reasoning_model | parser).invoke(
            {
                'format_instructions': parser.get_format_instructions(),
                'payload': json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
            }
        )
        return validate_wake_word_adjudication(
            raw,
            matched_segment_ids=matched_ids,
            transcript_segments=transcript_segments,
        )
    except Exception as error:
        logger.error('Error adjudicating wake-word invocations: %s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='wake_word_adjudication',
            to_mode='capture_review',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return WakeWordAdjudication()


__all__ = [
    'WAKE_WORD_ADJUDICATION_PROMPT',
    'WakeWordAdjudication',
    'WakeWordInvocationVerdict',
    'WakeWordInvocationVerdictValue',
    'adjudicate_wake_word_invocations',
    'validate_wake_word_adjudication',
]
