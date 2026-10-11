"""Independent spelling support and the shared Review spelling question shape."""

import hashlib
import re
import unicodedata
from datetime import datetime, timezone

from models.review import ReviewItem, SpellingItem


def source_conversations(ref, row):
    sources = {ref.split('/', 1)[1]} if ref.startswith('conversations/') else set()
    if row.get('conversation_id'):
        sources.add(row['conversation_id'].removeprefix('conversations/'))
    for item in [*(row.get('provenance') or []), *(row.get('evidence') or [])]:
        if isinstance(item, dict) and item.get('kind') == 'conversation' and item.get('id'):
            sources.add(item['id'])
        if isinstance(item, dict) and item.get('conversation_id'):
            sources.add(item['conversation_id'])
    return sources


def record_text(row):
    values = [row.get(key) for key in ('name', 'label', 'content', 'description', 'summary', 'title')]
    values.extend((row.get('structured') or {}).get(key) for key in ('title', 'overview'))
    values.extend(segment.get('text') for segment in row.get('transcript_segments') or [])
    values.extend(row.get('aliases') or [])
    return '\n'.join(value for value in values if isinstance(value, str))


def contains_spelling(value, spelling):
    normalize = lambda text: unicodedata.normalize('NFC', text.casefold())
    return bool(re.search(r'(?<!\w)' + re.escape(normalize(spelling.strip())) + r'(?!\w)', normalize(value)))


def spelling_grounding_rejection(edit, records, vocabulary=()):
    if edit.kind != 'spelling':
        return None
    if (
        not edit.before.strip()
        or not edit.after.strip()
        or max(len(edit.before), len(edit.after)) > 50
        or edit.before == edit.after
    ):
        return 'invalid_spelling'
    target = records.get(edit.target)
    if target is None or any(ref not in records for ref in edit.evidence):
        return 'invalid_evidence'
    sources = source_conversations(edit.target, target)
    for ref in edit.evidence:
        if ref == edit.target or ref.split('/', 1)[-1] == edit.target.split('/', 1)[-1]:
            continue
        row = records[ref]
        if sources & source_conversations(ref, row):
            continue
        if contains_spelling(record_text(row), edit.after):
            return None
    if any(
        contains_spelling(value, edit.after)
        for row in vocabulary
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
