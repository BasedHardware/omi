"""Semantic key payloads, excluding model prose and session identity."""

import json
from models.agent_refs import base_ref, cited_value, has_ref
from utils.agent_capabilities.text_edits import replace_term


def default(edit, records):
    return edit.kind, [edit.target, edit.other, edit.before.casefold(), edit.after.casefold()]


def memory(edit, records):
    if not records or not has_ref(edit.target, records):
        return default(edit, records)
    row = records[base_ref(edit.target)]
    after = replace_term(row['content'], edit.before, edit.after) if edit.kind == 'spelling' else edit.after
    return 'memory', [
        row['content'],
        after,
        *[row.get(k) for k in ('subject_scope', 'subject_entity_id', 'slot', 'visibility')],
    ]


def spelling(edit, records):
    if records and base_ref(edit.target).split('/')[0] in {'memories', 'memory_items'}:
        return memory(edit, records)
    kind, value = default(edit, records)
    segment = cited_value(edit.target, records) if records and '#' in edit.target else None
    if segment:
        value[0] = [base_ref(edit.target), segment.get('id') or segment.get('segment_id') or segment.get('start')]
    return kind, value


def merge(edit, records):
    return edit.kind, sorted([edit.target, edit.other])


def merge_memory(edit, records):
    if not records or not has_ref(edit.target, records) or not has_ref(edit.other, records):
        return merge(edit, records)
    return edit.kind, sorted(
        json.dumps([row.get('content'), row.get('subject_entity_id'), row.get('slot')], sort_keys=True)
        for row in [records[base_ref(edit.target)], records[base_ref(edit.other)]]
    )


def hygiene(edit, records):
    if not records or not has_ref(edit.target, records):
        return default(edit, records)
    row = records[base_ref(edit.target)]
    replacement = edit.after or (records.get(base_ref(edit.other), {}).get('content') if edit.other else '')
    return edit.kind, [
        row.get('content'),
        replacement,
        *[row.get(k) for k in ('subject_scope', 'subject_entity_id', 'slot', 'visibility')],
    ]


def retire(edit, records):
    if not records or not has_ref(edit.target, records):
        return default(edit, records)
    row = records[base_ref(edit.target)]
    return edit.kind, [base_ref(edit.target), row.get('description') or row.get('name')]


def vocabulary(term, records):
    return 'vocabulary', [term.kind, term.spelling.casefold(), sorted(alias.casefold() for alias in term.aliases)]
