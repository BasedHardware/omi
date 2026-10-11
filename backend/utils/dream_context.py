"""Bounded target neighbourhoods, cheapest first, using existing read indexes."""

from datetime import timedelta
from difflib import SequenceMatcher

from database import action_items, conversations, screen_activity, vector_db
from utils.conversations.search import keyword_search_conversation_ids
from utils.dream_guards import common_words, timestamp, tokens
from utils.dream_prompt import (
    project_record,
    fits_triage,
    evidence_message,
    triage_budget,
    mount,
    COMPLETION_RESERVE,
    TRIAGE_INSTRUCTIONS,
    person_names,
)
from utils.dream_transport import input_ceiling
from models.dream_agent import Triage, Plan
from utils.memory.memory_service import MemoryService


class EvidenceRecords(dict):
    """Roles live outside storage snapshots so Review fingerprints stay intact."""

    def __init__(self, records=(), *, targets=None):
        super().__init__(records)
        self.targets = set(self if targets is None else targets)


def target_refs(records):
    return getattr(records, 'targets', set(records))


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


def query_terms(row, vocabulary=()):
    text = (
        project_record('conversations/query', row, chars=3000, names={})
        if 'transcript_segments' in row
        else ' '.join(str(row.get(key) or '') for key in ('name', 'content', 'description', 'summary', 'label'))
    )
    words = list(dict.fromkeys(word for word in tokens(text) if len(word) > 3 and word not in common_words()))
    near = [
        entry['spelling']
        for entry in vocabulary
        if entry.get('spelling')
        and any(SequenceMatcher(None, word, entry['spelling'].casefold()).ratio() >= 0.75 for word in words)
    ]
    return list(dict.fromkeys([*words, *near]))[:6]


def identities(row):
    refs = {row[key] for key in ('subject_entity_id', 'workstream_id') if row.get(key)}
    refs.update(
        'person:' + segment['person_id'] for segment in row.get('transcript_segments') or [] if segment.get('person_id')
    )
    return refs


def context_candidates(uid, targets, vocabulary, *, read_record, read_entity_record):
    """Yield lazily: once the evidence budget is full no later-tier query runs."""
    if not target_refs(targets):
        return
    subjects = set().union(*(identities(row) for row in targets.values()))
    for entity_id in sorted(subjects)[:8]:
        yield 'entity/' + entity_id, read_entity_record(uid, entity_id)
    for ref, row in targets.items():
        linked = row.get('conversation_id')
        if linked:
            linked_ref = 'conversations/' + linked.removeprefix('conversations/')
            yield linked_ref, read_record(uid, linked_ref)
        if ref.startswith('conversations/'):
            for task in action_items.get_action_items(uid, conversation_id=ref.split('/', 1)[1], limit=8):
                task_ref = 'action_items/' + task['id']
                yield task_ref, read_record(uid, task_ref)
    # Bounded canonical list: same-subject facts, then lexical candidates.
    memories = MemoryService().read(uid, limit=40, authoritative=True)
    pool = {'memory_items/' + memory.id: memory.model_dump(mode='python') for memory in memories}
    for ref, row in pool.items():
        if identities(row) & subjects:
            yield ref, read_record(uid, ref)
    queries = list(dict.fromkeys(' '.join(query_terms(row, vocabulary)) for row in targets.values()))[:4]
    for query in filter(None, queries):
        for ref, row in pool.items():
            if set(tokens(query)) & set(tokens(row.get('content') or '')):
                yield ref, read_record(uid, ref)
        for key in keyword_search_conversation_ids(uid=uid, query=query, limit=4, raise_on_error=True):
            ref = 'conversations/' + key
            yield ref, read_record(uid, ref)
    for query in filter(None, queries):
        for key in vector_db.query_vectors(query, uid, k=3):
            ref = 'conversations/' + key
            yield ref, read_record(uid, ref)
        for match in MemoryService().search(uid, query, limit=3):
            ref = 'memory_items/' + match.memory.id
            yield ref, read_record(uid, ref)
    for row in list(targets.values())[:4]:
        time = timestamp(row.get('created_at') or row.get('timestamp'))
        if time is None:
            continue
        start, end = time - timedelta(hours=2), time + timedelta(hours=2)
        for neighbour in conversations.get_conversations(uid, start_date=start, end_date=end, limit=4):
            ref = 'conversations/' + neighbour['id']
            yield ref, read_record(uid, ref)
        for screen in screen_activity.get_screen_activity(uid, start_date=start, end_date=end, limit=4):
            yield 'screen/' + screen['id'], screen


def add_context(targets, candidates, caps, vocabulary=None):
    records = EvidenceRecords(targets, targets=target_refs(targets))
    for ref, row in candidates:
        if ref in records or not row:
            continue
        candidate = EvidenceRecords({**records, ref: row}, targets=records.targets)
        if not fits_pass(candidate, caps, vocabulary):
            break
        records = candidate
    return records
