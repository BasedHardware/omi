"""Independent spelling support and the shared Review spelling question shape."""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from models.review import ReviewItem, SpellingItem
from utils.conversations.summary_selection import render_sections_markdown


def source_conversations(ref, row):
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
        row.get(key) for key in ('name', 'label', 'content', 'description', 'summary', 'title', 'ocrText', 'ocr_text')
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
    target = records.get(edit.target)
    if target is None or any(ref not in records for ref in edit.evidence):
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
            if ref == edit.target or ref.split('/', 1)[-1] == edit.target.split('/', 1)[-1]:
                return True
            if ref not in records:
                return True
            if ref not in visited:
                visited.add(ref)
                if traces_target(records[ref], visited):
                    return True
        return False

    for ref in edit.evidence:
        if ref == edit.target or ref.split('/', 1)[-1] == edit.target.split('/', 1)[-1]:
            continue
        row = records[ref]
        if sources & source_conversations(ref, row) or traces_target(row):
            continue
        if contains_spelling(record_text(row), edit.after, exact_case=exact_case):
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


def spelling_question(edit, *, now=None):
    key = hashlib.sha256((edit.target + '\0' + edit.before + '\0' + edit.after).encode()).hexdigest()
    return ReviewItem(
        item_id='spelling:' + key,
        kind='spelling',
        title='Which spelling is correct?',
        quote=edit.before,
        created_at=now or datetime.now(timezone.utc),
        spelling=SpellingItem(term_id=key, options=[edit.before, edit.after], allow_custom=True),
    )
