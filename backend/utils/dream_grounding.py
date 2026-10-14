"""Independent spelling support and the shared Review spelling question shape."""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from models.review import SpellingItem
from models.dream_agent import DreamReviewItem, FullReviewItem
from models.dream_refs import base_ref, has_ref, cited_value
from utils.conversations.summary_selection import render_sections_markdown


def source_conversations(ref, row):
    ref = base_ref(ref)
    sources = {ref.split('/', 1)[1]} if ref.startswith('conversations/') else set()
    if row.get('conversation_id'):
        sources.add(row['conversation_id'].removeprefix('conversations/'))
    for item in [*(row.get('provenance') or []), *(row.get('evidence') or [])]:
        if isinstance(item, dict) and item.get('kind') == 'conversation' and item.get('id'):
            sources.add(item['id'])
        if isinstance(item, dict) and item.get('conversation_id'):
            sources.add(item['conversation_id'])
        if isinstance(item, dict) and item.get('source_type') == 'conversation' and item.get('source_id'):
            sources.add(item['source_id'].removeprefix('conversations/'))
    return sources


def record_text(row):
    values = [
        row.get(key)
        for key in ('text', 'name', 'label', 'content', 'description', 'summary', 'title', 'ocrText', 'ocr_text')
    ]
    values.extend((row.get('structured') or {}).get(key) for key in ('title', 'overview'))
    values.append(render_sections_markdown((row.get('structured') or {}).get('sections') or []))
    values.extend(segment.get('text') for segment in row.get('transcript_segments') or [])
    values.extend(row.get('aliases') or [])
    return '\n'.join(value for value in values if isinstance(value, str))


def contains_spelling(value, spelling, *, exact_case=False):
    normalize = lambda text: unicodedata.normalize('NFC', text if exact_case else text.casefold())
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(spelling.strip())) + r'(?!\w)', normalize(value)))


def spelling_grounding_rejection(edit, records, vocabulary=()):
    if edit.kind != 'spelling':
        return None
    if (
        not edit.before.strip()
        or not edit.after.strip()
        or max(len(edit.before), len(edit.after)) > 50
        or edit.before.strip() == edit.after.strip()
    ):
        return 'invalid_spelling'
    target_ref = base_ref(edit.target)
    target = records.get(target_ref)
    if target is None or any(not has_ref(ref, records) for ref in edit.evidence):
        return 'invalid_evidence'
    sources = source_conversations(edit.target, target)
    exact_case = edit.before.casefold() == edit.after.casefold()

    def traces_target(row, visited=None):
        visited = set() if visited is None else visited
        if sources & source_conversations('', row):
            return True
        for ref in row.get('evidence') or []:
            if not isinstance(ref, str):
                continue
            ref = base_ref(ref)
            if ref == target_ref or ref.split('/', 1)[-1] == target_ref.split('/', 1)[-1]:
                return True
            if ref not in records:
                return True
            if ref not in visited:
                visited.add(ref)
                if traces_target(records[ref], visited):
                    return True
        return False

    for ref in edit.evidence:
        base = base_ref(ref)
        if base == target_ref or base.split('/', 1)[-1] == target_ref.split('/', 1)[-1]:
            continue
        row = records[base]
        if sources & source_conversations(ref, row) or traces_target(row):
            continue
        selected = cited_value(ref, records)
        if selected is not None and contains_spelling(record_text(selected), edit.after, exact_case=exact_case):
            return None
    if any(
        contains_spelling(value, edit.after, exact_case=exact_case)
        for row in vocabulary
        if row.get('authorship') in {'user_authored', 'user_accepted'} and not traces_target(row)
        for value in [row.get('spelling', ''), *(row.get('aliases') or [])]
        if isinstance(value, str)
    ):
        return None
    return 'ungrounded_spelling'


def spelling_question(edit, *, now=None, full=False):
    key = hashlib.sha256((edit.target + '\0' + edit.before + '\0' + edit.after).encode()).hexdigest()
    model = FullReviewItem if full else DreamReviewItem
    payload = {
        'item_id': 'spelling:' + key,
        'kind': 'spelling',
        'title': 'Which spelling is correct?',
        'quote': edit.before,
        'source_ref': edit.target,
        'created_at': now or datetime.now(timezone.utc),
        'spelling': SpellingItem(term_id=key, options=[edit.before, edit.after], allow_custom=True),
    }
    if full:
        payload.update(
            value=getattr(edit, 'value', None) or 1, why_it_matters='Clarifies future use of this name or term.'
        )
    item = model.model_validate(payload)
    item.set_agreement(edit.agreement, edit.samples)
    return item


def rank_questions(items, *, usage_sink=None):
    retained = [item for item in items if getattr(item, 'value', 1) > 2]
    if usage_sink is not None:
        usage_sink['questions_dropped_low_value'] = (
            usage_sink.get('questions_dropped_low_value', 0) + len(items) - len(retained)
        )
    return sorted(retained, key=lambda item: (item.agreement, item.value), reverse=True)
