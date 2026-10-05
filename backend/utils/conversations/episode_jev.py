"""Pure SystemOne evidence questions, shared by the gateway and offline evaluation."""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Sequence

from config.jev_decisions import JEV_MAX_STATE_CHARS
from utils.conversations.episode_selection import after_capture

JEV_SELECTOR_PROMPT = 'episode_systemone_v1'
LANE = 'episode_evidence'
QUESTION_VERSION = 'episode_connection_v1'


@dataclass(frozen=True)
class EvidenceQuestionBatch:
    state: str
    questions: dict[str, dict[str, Any]]
    item_ids: dict[str, tuple[str, ...]]


def _surface(item):
    try:
        content = json.loads(item.content)
    except (ValueError, TypeError):
        return None
    if not isinstance(content, dict):
        return None
    app = content.get('app_name') or content.get('app')
    window = content.get('window_title') or content.get('window')
    return (app, window) if app or window else None


def _consecutive(previous, item):
    if previous.source_kind != item.source_kind or not _surface(item) or _surface(previous) != _surface(item):
        return False
    try:
        delta = (datetime.fromisoformat(item.time) - datetime.fromisoformat(previous.time)).total_seconds()
        return 0 <= delta <= 90
    except (ValueError, TypeError):
        return False


def evidence_candidates(items: Sequence[Any], *, finished_at=None):
    """Group adjacent captures of the same known app/window; never guess a surface."""
    groups = []
    for item in items:
        if item.source_kind in {'speech', 'device_state'} or after_capture(item, finished_at):
            continue
        if groups and item.source_kind in {'screen_frame', 'screen_ocr'} and _consecutive(groups[-1][-1], item):
            groups[-1].append(item)
        else:
            groups.append([item])
    return groups


def evidence_question_batches(items, *, started_at, finished_at):
    """Keep speech/context bounded; split candidates before the client's state truncation."""
    speech = [i.model_dump(exclude_none=True) for i in items if i.source_kind == 'speech']
    context = [i.model_dump(exclude_none=True) for i in items if i.source_kind in {'roster', 'device_state'}]
    description = json.dumps(
        {
            'version': QUESTION_VERSION,
            'start': started_at,
            'end': finished_at,
            'speech_excerpt': json.dumps(speech, ensure_ascii=False)[:6000],
            'participants_and_capture': json.dumps(context, ensure_ascii=False)[:2000],
        },
        ensure_ascii=False,
    )
    batches, chunks, questions, ids = [], [], {}, {}
    for index, group in enumerate(evidence_candidates(items, finished_at=finished_at)):
        name = f'item_{index}'
        chunk = json.dumps(
            {'candidate': name, 'items': [i.model_dump(exclude_none=True) for i in group]}, ensure_ascii=False
        )
        question = {
            'type': 'noul',
            'instructions': f'Is candidate {name} connected to what happened in this conversation?',
            'criteria': {
                'true': 'An evidenced connection to speech, participants interacting, the active call, or observed owner activity; prior context explains a current reference.',
                'false': 'Incidental co-occurrence, shared vocabulary alone, unrelated document/chat, or an uncertain connection. An invite does not establish attendance.',
            },
        }
        # Questions also consume context. An individually oversize item fails open locally.
        if len(description) + len(chunk) + len(json.dumps(question)) > JEV_MAX_STATE_CHARS:
            raise ValueError('selection_oversize')
        if (
            len(description) + sum(map(len, chunks)) + len(chunk) + len(json.dumps({**questions, name: question}))
            > JEV_MAX_STATE_CHARS
        ):
            batches.append(EvidenceQuestionBatch(description + '\n' + '\n'.join(chunks), questions, ids))
            chunks, questions, ids = [], {}, {}
        chunks.append(chunk)
        questions[name] = question
        ids[name] = tuple(i.id for i in group)
    if questions:
        batches.append(EvidenceQuestionBatch(description + '\n' + '\n'.join(chunks), questions, ids))
    return batches


def scored_episode_items(items, batches, scores, *, threshold, finished_at=None):
    """Select exact original evidence, keeping speech and trusted capture constraints."""
    expected = {question for batch in batches for question in batch.questions}
    if set(scores) != expected or any(
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 1
        for score in scores.values()
    ):
        raise ValueError('invalid_jev_scores')
    selected = {
        item_id
        for batch in batches
        for q, item_ids in batch.item_ids.items()
        if scores[q] >= threshold
        for item_id in item_ids
    }
    return [
        item
        for item in items
        if item.source_kind == 'speech'
        or (not after_capture(item, finished_at) and (item.source_kind == 'device_state' or item.id in selected))
    ]
