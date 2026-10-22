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
from threading import Lock

from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.calls_metrics import observe

FLAG = 'STT_VOCAB_MODE'
STT_VOCAB_PERCENT = 'STT_VOCAB_MODE_SERVE_PERCENT'
STT_VOCAB_DIGESTS = 'STT_VOCAB_MODE_SERVE_UID_SHA256S'
MAX_TERMS = 100
MAX_CHARS = 2000
MAX_USERS = 128
TTL = 600
_cache = OrderedDict()
_lock = Lock()
_STOP = frozenset(
    'The This That They Their Then There When Where What Which While After Before During User Owner Someone One Another Today Yesterday Tomorrow Monday Tuesday Wednesday Thursday Friday Saturday Sunday'.casefold().split()
)
_PROPER = re.compile(r'\b[A-Z][\w]*(?:[ -][A-Z][\w]*){0,2}\b')


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
    from database.memories import get_memories
    from database.redis_db import get_enabled_apps, get_app_cache_by_id
    from database import dream_store

    people = list_people(get_firestore_client(), uid, limit=200)
    memories = get_memories(uid, limit=80)
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
    terms = _sources(uid)
    with _lock:
        _cache[uid] = (time.monotonic() + TTL, tuple(terms))
        _cache.move_to_end(uid)
        while len(_cache) > MAX_USERS:
            _cache.popitem(last=False)
    return list(terms)


async def apply_context(config, uid=None):
    if not shadow_or_serve(FLAG):
        return
    if uid is None:
        from utils.byok import get_byok_uid

        uid = get_byok_uid()
    if not uid:
        return
    try:
        from utils.executors import db_executor, run_blocking

        terms = await asyncio.wait_for(run_blocking(db_executor, cached_terms, uid), timeout=2)
        # Even in serve mode only the term count may enter telemetry.
        observe('stt_vocab', 'disagree' if terms else 'agree', size=len(terms))
        if terms and serving_for(FLAG, uid):
            config['context'] = {**config.get('context', {}), 'terms': terms}
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
