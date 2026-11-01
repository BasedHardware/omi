"""Bounded, verbatim speech excerpts from owner-scoped Review source snapshots."""

from datetime import datetime

from models.agent_refs import base_ref, cited_value
from models.review import SpellingContext, SpellingContextSegment

MAX_CONTEXT_CHARS = 400
MAIN_SEGMENT_CHARS = 300


def question_source(item, records):
    """Persist only this question's record and known speaker names, not the entire pass."""
    ref = base_ref(item.source_ref or '')
    row = records.get(ref)
    if item.kind != 'spelling' or not ref.startswith('conversations/') or not isinstance(row, dict):
        return {}
    names = {}
    for segment in row.get('transcript_segments') or []:
        person_id = segment.get('person_id')
        if person_id:
            person = records.get(f'people/{person_id}') or records.get(f'entity/person:{person_id}') or {}
            if person.get('name'):
                names[person_id] = person['name']
    return {'records': {ref: row}, 'speaker_names': names}


def _date(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    return None


def _utf16_offset(text):
    # Dart indexes UTF-16 code units; an emoji before the quote must not shift the highlight.
    return len(text.encode('utf-16-le')) // 2


def build_context(item, source, *, load_conversation=None):
    ref = item.source_ref or ''
    base = base_ref(ref)
    collection, separator, key = base.partition('/')
    if collection != 'conversations' or not separator or not key or '/' in key:
        return None
    records = source.get('records') or {}
    row = records.get(base)
    if row is None and load_conversation is not None:
        row = load_conversation(key)
    if not isinstance(row, dict):
        return None
    segments = row.get('transcript_segments') or []
    if not segments:
        return None
    quote = item.quote or ''
    if '#' in ref:
        selected = cited_value(ref, {base: row})
        index = next((i for i, segment in enumerate(segments) if segment is selected), None)
    else:
        index = next((i for i, segment in enumerate(segments) if quote and quote in segment.get('text', '')), None)
    if index is None:
        return None
    main = segments[index].get('text') or ''
    match = main.find(quote) if quote else -1
    # Keep a long quote intact whenever it fits the overall excerpt budget.
    main_limit = min(MAX_CONTEXT_CHARS, max(MAIN_SEGMENT_CHARS, len(quote)))
    start = max(0, min(match - max(0, (main_limit - len(quote)) // 2), len(main) - main_limit)) if match >= 0 else 0
    shown = main[start : start + main_limit]
    highlight = match >= start and match + len(quote) <= start + len(shown) and bool(quote)
    indices = list(range(max(0, index - 1), min(len(segments), index + 2)))
    neighbours = len(indices) - 1
    remaining = MAX_CONTEXT_CHARS - len(shown)
    names = source.get('speaker_names') or {}
    lines = []
    for i in indices:
        segment = segments[i]
        text = segment.get('text') or ''
        if i == index:
            text = shown
        else:
            budget = remaining // neighbours
            text = text[-budget:] if i < index and budget else text[:budget]
            remaining -= len(text)
            neighbours -= 1
        is_user = segment.get('is_user') is True
        name = names.get(segment.get('person_id')) or segment.get('person_name') or segment.get('speaker_label')
        lines.append(SpellingContextSegment(text=text, is_user=is_user, speaker_label='You' if is_user else name))
    return SpellingContext(
        conversation_title=row.get('user_title')
        or (row.get('structured') or {}).get('title')
        or row.get('title')
        or '',
        conversation_date=_date(row.get('started_at') or row.get('created_at')),
        segments=lines,
        main_index=indices.index(index),
        quote_start=_utf16_offset(shown[: match - start]) if highlight else None,
        quote_end=_utf16_offset(shown[: match - start + len(quote)]) if highlight else None,
    )


def enrich_spelling(item, source, *, load_conversation=None, overwrite=False):
    if item.spelling is not None and (overwrite or item.spelling.context is None):
        context = build_context(item, source, load_conversation=load_conversation)
        item = item.model_copy(update={'spelling': item.spelling.model_copy(update={'context': context})})
    return item
