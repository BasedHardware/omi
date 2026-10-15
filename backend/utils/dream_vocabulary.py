"""Optional capture-time vocabulary, never a live-session dependency."""

import os

from database import dream_store
from utils.executors import db_executor, run_blocking
from utils.observability.fallback import record_fallback


async def keyterms(uid, existing):
    if os.getenv('DREAM_AGENT_VOCABULARY_STT', 'false').lower() != 'true':
        return existing
    try:
        terms = await run_blocking(db_executor, dream_store.vocabulary, uid)
        result = list(dict.fromkeys([*existing, *[term['spelling'] for term in terms]]))
        return [term for term in result if isinstance(term, str) and len(term) <= 50][:100]
    except Exception:
        record_fallback(
            component='stt_live_session',
            from_mode='vocabulary',
            to_mode='existing_terms',
            reason='dependency_unavailable',
            outcome='degraded',
        )
        return existing
