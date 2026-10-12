"""Bounded target neighbourhoods, cheapest first, using existing read indexes."""

from datetime import timedelta
from functools import partial
from difflib import SequenceMatcher

from database import action_items, vector_db
from database.dream_context_reads import temporal_neighbours, subject_memory_refs
from utils.observability.fallback import record_fallback
from utils.conversations.search import keyword_search_conversation_ids
from utils.dream_guards import common_words, timestamp, tokens
from utils.dream_prompt import (
    fits_triage,
    evidence_message,
    triage_budget,
    mount,
    COMPLETION_RESERVE,
    TRIAGE_INSTRUCTIONS,
    person_names,
    text,
)
from utils.dream_transport import input_ceiling
from models.dream_agent import Triage, Plan
from fastapi import HTTPException
from database import review_store
from utils.memory.memory_service import MemoryService
from utils.executors import llm_executor, submit_with_context
from utils.dream_diagnostics import path_count, path_failure


class EvidenceRecords(dict):
    """Roles live outside storage snapshots so Review fingerprints stay intact."""

    def __init__(self, records=(), *, targets=None):
        super().__init__(records)
        self.targets = set(self if targets is None else targets)


def target_refs(records):
    return getattr(records, 'targets', set(records))


REASONING_TARGET_LIMIT = 8


PROBLEMS = ('spelling', 'duplicates', 'entity', 'tasks', 'quality')


def cluster_hints(triage, records):
    # A compact union per problem preserves every admitted evidence association.
    # Repeated clusters/refs cannot inflate the paid reasoning metadata.
    return {
        'clusters': [
            {
                'problem': problem,
                'refs': sorted(
                    {
                        ref
                        for cluster in triage.clusters
                        if cluster.problem == problem
                        for ref in cluster.refs
                        if ref in records
                    }
                ),
            }
            for problem in PROBLEMS
            if any(cluster.problem == problem for cluster in triage.clusters)
        ]
    }


def fits_pass(records, caps, vocabulary=None):
    if not fits_triage(records, caps, vocabulary):
        return False
    # Reserve the worst case triage input + its completion before admitting context.
    try:
        budget = triage_budget(caps)
        triage = evidence_message(records, Triage, budget, vocabulary=vocabulary)
        ceiling = input_ceiling(mount(Triage, budget, TRIAGE_INSTRUCTIONS).messages(triage), Triage.model_json_schema())
        worst_clusters = {'clusters': [{'problem': problem, 'refs': list(records)} for problem in PROBLEMS]}
        evidence_message(
            records,
            Plan,
            caps.tokens - ceiling - COMPLETION_RESERVE,
            vocabulary=vocabulary,
            clusters=worst_clusters,
            names=person_names(records),
        )
    except ValueError:
        return False
    return True


QUERY_STOP_WORDS = frozenset(
    'a an and are as at be been but by can could did do does for from had has have '
    'he her here him his how i if in is it its just me my no not of on or our she '
    'so than that the their them then there these they this those to too us was '
    'we were what when where which who why will with would yes you your'.split()
)


def query_content(row):
    # Query content, never the projector's synthetic "title/overview" headers.
    return ' '.join(
        [str(row.get('user_title') or '')]
        + [str((row.get('structured') or {}).get(key) or '') for key in ('title', 'overview')]
        + [str(row.get(key) or '') for key in ('name', 'content', 'description', 'summary', 'label')]
        + [text(segment.get('text')) for segment in row.get('transcript_segments') or []]
    )[:3000]


def query_terms(row, vocabulary=()):
    words = list(dict.fromkeys(word for word in tokens(query_content(row)) if len(word) >= 3))
    rare = [word for word in words if word not in common_words()]
    near = [
        entry['spelling']
        for entry in vocabulary
        if entry.get('spelling')
        and any(SequenceMatcher(None, word, entry['spelling'].casefold()).ratio() >= 0.75 for word in words)
    ]
    # Rarity prioritizes spelling anchors; ordinary speech must still search.
    preferred = rare or [word for word in words if word not in QUERY_STOP_WORDS]
    return list(dict.fromkeys([*near[:2], *preferred]))[:6]


def identities(row):
    refs = {row[key] for key in ('subject_entity_id', 'workstream_id') if row.get(key)}
    refs.update(
        'person:' + segment['person_id'] for segment in row.get('transcript_segments') or [] if segment.get('person_id')
    )
    return refs


def semantic_conversation_refs(query, uid):
    # The shared search API intentionally returns [] when unconfigured; Dream
    # diagnostics must distinguish an unavailable index from a healthy no-hit.
    if vector_db.index is None:
        raise RuntimeError('Conversation vector index unavailable')
    return vector_db.query_vectors(query, uid, k=3)


def query_candidates(report, path, query):
    """Count provider calls separately from returned references and hydration."""
    path_count(report, path, 'attempted')
    try:
        rows = list(query())
        path_count(report, path, 'found', len(rows))
        yield from rows
    except Exception as exc:
        path_failure(report, path, exc)
        record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')


def context_candidates(
    uid, targets, vocabulary, *, read_record, read_entity_record, diagnostics=None, excluded_refs=None
):
    """Yield lazily: once the evidence budget is full no later-tier query runs."""
    if not target_refs(targets):
        return
    diagnostics = {} if diagnostics is None else diagnostics
    # Include unseeded targets and already supplied context in temporal exclusion.
    excluded = set(targets) if excluded_refs is None else excluded_refs
    targets = {ref: row for ref, row in targets.items() if ref in target_refs(targets)}
    subjects = set().union(*(identities(row) for row in targets.values()))
    for entity_id in sorted(subjects)[:8]:
        path_count(diagnostics, 'links', 'found')
        yield 'entity/' + entity_id, partial(read_entity_record, uid, entity_id), 'links'
    for ref, row in list(targets.items())[:4]:
        linked = row.get('conversation_id')
        if linked:
            linked_ref = 'conversations/' + linked.removeprefix('conversations/')
            path_count(diagnostics, 'links', 'found')
            yield linked_ref, partial(read_record, uid, linked_ref), 'links'
        if ref.startswith('conversations/'):
            for task in query_candidates(
                diagnostics,
                'links',
                partial(action_items.get_action_items, uid, conversation_id=ref.split('/', 1)[1], limit=8),
            ):
                task_ref = 'action_items/' + task['id']
                yield task_ref, partial(read_record, uid, task_ref), 'links'
    # Read only bounded same-subject references; never scan an unrelated memory list.
    for subject in sorted(subjects)[:8]:
        for ref in query_candidates(diagnostics, 'links', partial(subject_memory_refs, uid, subject)):
            yield ref, partial(read_record, uid, ref), 'links'
    lexical = [' '.join(query_terms(row, vocabulary)) for row in targets.values()]
    semantic = [query_content(row).strip()[:600] for row in targets.values()]
    path_count(diagnostics, 'lexical', 'query_empty', sum(not query for query in lexical))
    path_count(diagnostics, 'semantic', 'query_empty', sum(not query for query in semantic))
    for query in list(dict.fromkeys(filter(None, lexical)))[:4]:
        for key in query_candidates(
            diagnostics,
            'lexical',
            partial(keyword_search_conversation_ids, uid=uid, query=query, limit=4, raise_on_error=True),
        ):
            ref = 'conversations/' + key
            yield ref, partial(read_record, uid, ref), 'lexical'
    # Embeddings use bounded natural-language content, independent of rare tokens.
    for query in list(dict.fromkeys(filter(None, semantic)))[:4]:
        # These existing search APIs include synchronous embedding calls.
        for key in query_candidates(
            diagnostics,
            'semantic',
            lambda: submit_with_context(llm_executor, semantic_conversation_refs, query, uid).result(),
        ):
            ref = 'conversations/' + key
            yield ref, partial(read_record, uid, ref), 'semantic'
        for match in query_candidates(
            diagnostics,
            'semantic',
            lambda: submit_with_context(llm_executor, MemoryService().search, uid, query, limit=3).result(),
        ):
            ref = 'memory_items/' + match.memory.id
            yield ref, partial(read_record, uid, ref), 'semantic'
    for row in list(targets.values())[:4]:
        time = timestamp(row.get('created_at') or row.get('timestamp'))
        if time is None:
            continue
        for neighbour in query_candidates(
            diagnostics,
            'temporal',
            partial(
                temporal_neighbours,
                uid,
                'conversations',
                time - timedelta(hours=24),
                time,
                time + timedelta(hours=24),
                excluded_ids={ref.split('/', 1)[1] for ref in excluded if ref.startswith('conversations/')},
            ),
        ):
            ref = 'conversations/' + neighbour['id']
            yield ref, partial(read_record, uid, ref), 'temporal'
        for screen in query_candidates(
            diagnostics,
            'temporal',
            partial(
                temporal_neighbours,
                uid,
                'screen_activity',
                time - timedelta(hours=2),
                time,
                time + timedelta(hours=2),
                excluded_ids={ref.split('/', 1)[1] for ref in excluded if ref.startswith('screen/')},
            ),
        ):
            yield 'screen/' + screen['id'], screen, 'temporal'


def add_context(targets, candidates, caps, vocabulary=None, *, diagnostics=None, excluded_refs=None):
    diagnostics = {} if diagnostics is None else diagnostics
    records = EvidenceRecords(targets, targets=target_refs(targets))
    seen = set(records) if excluded_refs is None else excluded_refs
    seen.update(records)
    for ref, load, path in candidates:
        if ref in seen:
            path_count(diagnostics, path, 'duplicate')
            continue
        seen.add(ref)
        # Probe metadata only: a fabricated 1500-character row rejected short,
        # useful neighbours before reading them and prevented later tiers running.
        probe = EvidenceRecords(
            {**records, ref: {}},
            targets=records.targets,
        )
        if not fits_pass(probe, caps, vocabulary):
            path_count(diagnostics, path, 'budget_skipped')
            break
        if callable(load):
            path_count(diagnostics, path, 'attempted')
        try:
            row = load() if callable(load) else load
        except (review_store.ReviewNotFound, HTTPException) as exc:
            if isinstance(exc, review_store.ReviewNotFound) or exc.status_code in {402, 404, 423}:
                path_count(diagnostics, path, 'unavailable')
                continue
            seen.discard(ref)  # A later bounded path may recover a transient read failure.
            path_failure(diagnostics, path, exc)
            record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
            continue
        except Exception as exc:
            seen.discard(ref)  # A later bounded path may recover a transient read failure.
            path_failure(diagnostics, path, exc)
            record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
            continue
        if not row:
            path_count(diagnostics, path, 'unavailable')
            continue
        candidate = EvidenceRecords({**records, ref: row}, targets=records.targets)
        if not fits_pass(candidate, caps, vocabulary):
            path_count(diagnostics, path, 'budget_skipped')
            break
        records = candidate
        path_count(diagnostics, path, 'added')
    return records
