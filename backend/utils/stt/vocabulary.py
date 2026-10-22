"""Bounded per-user Soniox spelling vocabulary, independent of language hints.

Only terms are sent (never memory sentences). Source reads run off the event
loop. Cache entries expire in ten minutes and the process keeps at most 128.
Provider contract: https://soniox.com/docs/stt/concepts/context
"""

import asyncio
import re
import time
import unicodedata
from collections import Counter, OrderedDict
from threading import Lock, BoundedSemaphore

from config.refactor_modes import serving_for, shadow_or_serve, shadow_sampled
from utils.conversations.calls_metrics import observe

FLAG_ENV = 'STT_VOCAB_MODE'
FLAG = FLAG_ENV
STT_VOCAB_SHADOW_PERCENT_ENV = 'STT_VOCAB_MODE_SHADOW_PERCENT'
MAX_TERMS = 100
MAX_CHARS = 2000
MAX_USERS = 128
TTL = 600
_cache = OrderedDict()
_lock = Lock()
_fills = BoundedSemaphore(4)
_loading = set()
_STOP = frozenset(
    'The This That They Their Then There When Where What Which While After Before During User Owner Someone One Another Today Yesterday Tomorrow Monday Tuesday Wednesday Thursday Friday Saturday Sunday'.casefold().split()
)
_PROPER = re.compile(r'\b(?:[A-Z][\w]*(?:[ -][A-Z][\w]*){0,2}|[a-z][a-z0-9]*\d[a-z0-9]*)\b')


def bounded_terms(values):
    terms, seen, size = [], set(), 0
    for value in values:
        if not isinstance(value, str):
            continue
        term = ' '.join(unicodedata.normalize('NFKC', value).split())
        if not 2 <= len(term) <= 60 or any(unicodedata.category(c).startswith('C') for c in term):
            continue
        if not any(c.isalpha() for c in term) or '@' in term or '://' in term:
            continue
        key = term.casefold()
        if key in seen or key in _STOP or size + len(term) > MAX_CHARS:
            continue
        terms.append(term)
        seen.add(key)
        size += len(term)
        if len(terms) >= MAX_TERMS:
            break
    return terms


def build_terms(people, memories, apps, vocabulary=()):
    # Count presence per memory, so a repeated phrase in one memory is not frequent.
    counts, spellings = Counter(), {}
    for memory in memories[:80]:
        text = str(memory.get('content') or '')[:2000]
        found = {}
        for match in _PROPER.finditer(text):
            term = match.group()
            key = term.casefold()
            if key not in _STOP:
                found[key] = term
        counts.update(found.keys())
        spellings.update(found)
    frequent = [spellings[key] for key in sorted(counts, key=lambda k: (-counts[k], k)) if counts[key] >= 2]
    names = [row.get('name') for row in people[:200]]
    products = [row.get('name') for row in apps[:20]]
    learned = [row.get('spelling') for row in vocabulary[:100]]
    # Interleave sources so contacts cannot crowd out products and frequent nouns.
    from itertools import zip_longest

    return bounded_terms(value for group in zip_longest(names, products, learned, frequent) for value in group)


def _sources(uid):
    from database._client import get_firestore_client
    from database.person_aliases import list_people
    from utils.memory.memory_service import MemoryService
    from utils.other.list_budget import ListReadBudget
    from database.redis_db import get_enabled_apps, get_app_cache_by_id
    from database import dream_store

    people = list_people(get_firestore_client(), uid, limit=200)
    budget = ListReadBudget(deadline_monotonic=time.monotonic() + 1.5, max_documents=240)
    memories = [
        {'content': row.content} for row in MemoryService().read(uid, limit=80, budget=budget) if not row.is_locked
    ]
    apps = [get_app_cache_by_id(app_id) or {} for app_id in (get_enabled_apps(uid) or [])[:20]]
    return build_terms(people, memories, apps, dream_store.vocabulary(uid) or [])


def cached_terms(uid):
    now = time.monotonic()
    with _lock:
        for key in list(_cache):
            if _cache[key][0] <= now:
                del _cache[key]
        if uid in _cache:
            _cache.move_to_end(uid)
            return list(_cache[uid][1])
    if not _fills.acquire(blocking=False):
        return []
    with _lock:
        if uid in _loading:
            _fills.release()
            return []
        _loading.add(uid)
    try:
        terms = _sources(uid)
    finally:
        with _lock:
            _loading.discard(uid)
        _fills.release()
    with _lock:
        _cache[uid] = (time.monotonic() + TTL, tuple(terms))
        _cache.move_to_end(uid)
        while len(_cache) > MAX_USERS:
            _cache.popitem(last=False)
    return list(terms)


async def _load_terms(uid):
    try:
        from utils.executors import db_executor, run_blocking

        terms = await asyncio.wait_for(run_blocking(db_executor, cached_terms, uid), timeout=2)
        # Even in serve mode only the term count may enter telemetry.
        observe('stt_vocab', 'agree' if terms else 'disagree', size=len(terms))
        return terms
    except Exception:
        observe('stt_vocab', 'error')
        if serving_for(FLAG, uid):
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='stt_live_session',
                from_mode='custom_vocabulary',
                to_mode='unbiased_transcription',
                reason='dependency_unavailable',
                outcome='degraded',
            )
        return []


async def apply_context(config, uid=None):
    if not shadow_or_serve(FLAG):
        return
    if not uid or not shadow_sampled(FLAG, uid, default_percent=1.0):
        return
    if not serving_for(FLAG, uid):
        from utils.executors import start_background_task

        start_background_task(_load_terms(uid), name='soniox_vocabulary_shadow')
        return
    terms = await _load_terms(uid)
    if terms:
        config['context'] = {**config.get('context', {}), 'terms': terms}
