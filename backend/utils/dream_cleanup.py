"""Stochastic, age-weighted cleanup seeds; neighbourhoods remain read-only."""

import random
from uuid import UUID
from utils.observability.fallback import record_fallback
from datetime import timedelta
from difflib import SequenceMatcher

from config.dream_agent import backfill_share, random_seed_share
from database import dream_history
from utils.dream_context import EvidenceRecords, fits_pass, identities, query_terms
from utils.dream_guards import MIN_RETIRE_TASK_DAYS, normalized, summary_eligibility, timestamp

REVIEW_DAYS = 30
SEED_MIN_DAYS = 7


def eligible_seed(row, last_reviewed_at, now):
    created = timestamp(row.get('created_at'))
    reviewed = timestamp(last_reviewed_at)
    return (
        not row.get('pinned')
        and created is not None
        and created <= now - timedelta(days=SEED_MIN_DAYS)
        and (last_reviewed_at is None or (reviewed is not None and reviewed <= now - timedelta(days=REVIEW_DAYS)))
    )


def problem_score(ref, row, pool, now):
    collection = ref.split('/', 1)[0]
    if collection == 'conversations':
        return sum(value == 'editable' for value in summary_eligibility(row).values())
    if collection == 'action_items':
        created = timestamp(row.get('created_at'))
        return (
            2
            if created
            and now - created > timedelta(days=MIN_RETIRE_TASK_DAYS)
            and row.get('status', 'active') == 'active'
            and not row.get('completed')
            else 0
        )
    if collection in {'people', 'memory_items'}:
        return 3 if any(duplicate_pair(ref, row, other_ref, other) for other_ref, other in pool.items()) else 0
    return 0


def duplicate_pair(ref, row, other_ref, other):
    collection = ref.split('/', 1)[0]
    if ref == other_ref or other_ref.split('/', 1)[0] != collection or collection not in {'people', 'memory_items'}:
        return False
    if collection == 'people' and (row.get('pinned') or other.get('pinned')):
        return False
    field, threshold, length = ('name', 0.88, 120) if collection == 'people' else ('content', 0.92, 800)
    if collection == 'memory_items' and any(
        row.get(key) != other.get(key) for key in ('subject_scope', 'subject_entity_id', 'slot', 'visibility')
    ):
        return False
    value = normalized(row.get(field) or '')
    candidate = normalized(other.get(field) or '')
    # Do not treat long records with equal prefixes as duplicates.
    if len(value) < 4 or max(len(value), len(candidate)) > length:
        return False
    return SequenceMatcher(None, value, candidate).ratio() >= threshold


def related_to_targets(row, records):
    if not records.targets:
        return True
    words = set(query_terms(row))
    time = timestamp(row.get('created_at'))
    for ref in records.targets:
        other = records[ref]
        other_time = timestamp(other.get('created_at'))
        if identities(row) & identities(other) or words & set(query_terms(other)):
            return True
        if time and other_time and abs((time - other_time).total_seconds()) <= 7 * 86400:
            return True
    return False


def choose_weighted(pool, reviewed, now, rng):
    refs, weights = [], []
    for ref, row in pool.items():
        if not eligible_seed(row, reviewed.get(ref), now):
            continue
        score = problem_score(ref, row, pool, now)
        previous = timestamp(reviewed.get(ref)) or timestamp(row.get('created_at'))
        if score and previous:
            refs.append(ref)
            weights.append(score * max(1, (now - previous).total_seconds() / 86400))
    return rng.choices(refs, weights=weights, k=1)[0] if refs else None


def uniform_ref(uid, rng):
    counts = [(collection, dream_history.history_count(uid, collection)) for collection in dream_history.COLLECTIONS]
    size = sum(count for _, count in counts)
    if not size:
        return None
    rank = rng.randrange(size)
    for collection, count in counts:
        if rank < count:
            # UUID owner IDs; memory IDs also include content hashes and opaque prefixes.
            # A random-key successor has gap bias, unlike an offset/rank sample.
            key = (
                str(UUID(int=rng.getrandbits(128)))
                if collection != 'memory_items'
                else ''.join(
                    rng.choice('0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-') for _ in range(20)
                )
            )
            key = dream_history.history_from_key(uid, collection, key)
            return collection + '/' + key if key else None
        rank -= count
    return None


def add_seed(uid, records, lease, caps, vocabulary, *, read_record, rng=None):
    rng = rng or random.SystemRandom()
    cursor = dict(lease.get('cleanup_cursor') or {})
    records.target_sources = dict(getattr(records, 'target_sources', {ref: 'dirty' for ref in records.targets}))
    records.cleanup_cursor = cursor
    if lease.get('canary') or not lease.get('cleanup_selected', rng.random() < backfill_share()):
        return records
    source = 'random' if rng.random() < random_seed_share() else 'seeded'
    if source == 'random':
        ref = uniform_ref(uid, rng)
        pool = {ref: read_record(uid, ref)} if ref else {}
        pool = {ref: row for ref, row in pool.items() if row}
        reviewed = dream_history.last_reviewed(uid, pool)
        ref = next(
            (ref for ref, row in pool.items() if eligible_seed(row, reviewed.get(ref), lease['started_at'])), None
        )
    else:
        collection = rng.choice(dream_history.COLLECTIONS)
        ids = dream_history.history_page(uid, collection, after=cursor.get(collection))
        cursor[collection] = ids[-1] if ids else None
        refs = [collection + '/' + key for key in ids]
        reviewed = dream_history.last_reviewed(uid, refs)
        pool = {}
        for key in ids:
            ref = collection + '/' + key
            previous = timestamp(reviewed.get(ref))
            if reviewed.get(ref) is not None and (
                previous is None or previous > lease['started_at'] - timedelta(days=REVIEW_DAYS)
            ):
                continue
            row = read_record(uid, ref)
            if row:
                pool[ref] = row
        ref = choose_weighted(pool, reviewed, lease['started_at'], rng)
    if ref and ref not in records and related_to_targets(pool[ref], records):
        seeds = [ref]
        # A duplicate proposal needs two editable operands, not a context operand.
        if source == 'seeded':
            partner = next(
                (
                    other
                    for other, row in pool.items()
                    if eligible_seed(row, reviewed.get(other), lease['started_at'])
                    and duplicate_pair(ref, pool[ref], other, row)
                ),
                None,
            )
            if partner and partner not in records:
                seeds.append(partner)
        candidate = EvidenceRecords(
            {**records, **{key: pool[key] for key in seeds}}, targets={*records.targets, *seeds}
        )
        if fits_pass(candidate, caps, vocabulary):
            candidate.target_sources = {**records.target_sources, **{key: source for key in seeds}}
            candidate.cleanup_cursor = cursor
            return candidate
    return records


def add_seed_safely(uid, records, lease, caps, vocabulary, *, read_record):
    try:
        return add_seed(uid, records, lease, caps, vocabulary, read_record=read_record)
    except Exception:
        records.seed_errors = getattr(records, 'seed_errors', 0) + 1
        record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')
        return records
