"""Owner-visible before/after and speech context on every Dream journal entry."""

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from models.agent_refs import base_ref, cited_value
from models.review import ReviewChange
from models.review_context import build_context, question_source


def label(row):
    return ' '.join(
        str(
            row.get('content')
            or row.get('description')
            or row.get('name')
            or (row.get('structured') or {}).get('title')
            or 'Item'
        ).split()
    )[:4000]


def change_id_for_key(uid, key):
    return str(uuid5(NAMESPACE_URL, uid + ':' + key))


def edit_change(uid, edit, records, key):
    from utils.agent_capabilities.registry import get_kind

    before, after, refs = get_kind(edit.kind).change_view(edit, records)
    source_ref = (
        edit.target
        if edit.target.startswith('conversations/')
        else next((ref for ref in edit.evidence if ref.startswith('conversations/')), '')
    )
    selected = cited_value(source_ref, records) if '#' in source_ref else None
    quote = (
        edit.before
        if edit.kind == 'spelling'
        else (
            (selected or {}).get('text')
            or next(
                (
                    segment.get('text')
                    for segment in (records.get(base_ref(source_ref), {}).get('transcript_segments') or [])
                    if segment.get('text')
                ),
                '',
            )
        )[:200]
    )
    item = SimpleNamespace(kind='spelling', source_ref=source_ref, quote=quote)
    source = question_source(item, records)
    context = build_context(item, source)
    if (context is None or context.quote_start is None) and edit.kind == 'spelling' and edit.after:
        # Summary-only typos may already be spelled correctly in the speech.
        # Show that actual sentence instead of fabricating a transcript quote.
        context = build_context(SimpleNamespace(kind='spelling', source_ref=source_ref, quote=edit.after), source)
    return ReviewChange(
        change_id=change_id_for_key(uid, key),
        kind='other',
        title=edit.kind.replace('_', ' ').capitalize(),
        reason=edit.reason,
        edit_kind=edit.kind,
        before=before[:4000],
        after=after[:4000],
        context=context,
        refs=refs,
        created_at=datetime.now(timezone.utc),
    )
