"""One-time (idempotent) backfill of per-person context for EVERY person.

The connectors enrich a person incrementally as each NEW conversation is ingested
(see person_messaging_enrichment), but a user who connects with months of existing
history needs their whole roster enriched up front — otherwise every contact reads as
"no relationship" until they happen to text again. `backfill_people` walks the roster,
extracts per-person facts from each person's existing conversations, and (re)builds their
profile. Safe to re-run: fact writes dedup/supersede, and profile generation self-gates on
staleness. Meant to be kicked off once after the first sync (and callable on demand).
"""

import logging
from typing import Dict, List, Optional

from database import conversations as conversations_db
from database import redis_db
from database import users as users_db
from database.entities import person_entity_id
from models.conversation import Conversation
from utils.memory.person_messaging_enrichment import enrich_persons_from_conversation
from utils.llm.person_profile import generate_person_profile

logger = logging.getLogger(__name__)

# Redis flag so the whole-roster backfill runs at most once per user (first sync).
_BACKFILL_FLAG = "person_backfill:v1:{uid}"

# Skip people with essentially no captured history — nothing to build a profile from.
_MIN_SEGMENTS = 6
# Cap conversations read per person so one very chatty contact can't dominate a backfill run.
_CONV_LIMIT = 20


def _has_enough_history(convos: List[dict]) -> int:
    return sum(len(c.get("transcript_segments") or []) for c in convos)


def backfill_person(uid: str, person_id: str, *, language: Optional[str] = None, force_profile: bool = False) -> dict:
    """Enrich a single person from their existing conversations: extract per-person facts
    from each 1:1 conversation, then (re)build the profile. Returns a small summary dict."""
    result = {"person_id": person_id, "facts_written": 0, "profile_updated": False, "conversations": 0}
    try:
        convos = conversations_db.get_conversations_by_person_id(uid, person_id, limit=_CONV_LIMIT) or []
        result["conversations"] = len(convos)
        if _has_enough_history(convos) < _MIN_SEGMENTS:
            return result
        for c in convos:
            # enrich_persons_from_conversation applies its own source/1:1 gating + dedup, so
            # a group window is skipped and a re-run supersedes rather than duplicates.
            try:
                counts = enrich_persons_from_conversation(uid, Conversation(**c), language=language)
                result["facts_written"] += int(counts.get(person_id) or 0)
            except Exception as e:
                logger.warning(f"person_backfill: enrich conv failed uid={uid} person={person_id}: {e}")
        result["profile_updated"] = bool(generate_person_profile(uid, person_id, force=force_profile))
    except Exception as e:
        logger.warning(f"person_backfill: backfill_person failed uid={uid} person={person_id}: {e}")
    return result


def backfill_people(
    uid: str, *, max_people: Optional[int] = None, language: Optional[str] = None, force_profile: bool = False
) -> Dict[str, int]:
    """Backfill every person that has captured history. Idempotent and fully guarded — a
    failure on one person never aborts the run. Returns roster-level counters."""
    summary = {"people_seen": 0, "people_enriched": 0, "facts_written": 0, "profiles_updated": 0}
    try:
        people = users_db.get_people(uid) or []
    except Exception as e:
        logger.error(f"person_backfill: roster fetch failed uid={uid}: {e}")
        return summary
    for person in people:
        pid = person.get("id")
        if not pid:
            continue
        summary["people_seen"] += 1
        r = backfill_person(uid, pid, language=language, force_profile=force_profile)
        if r["facts_written"] or r["profile_updated"]:
            summary["people_enriched"] += 1
        summary["facts_written"] += r["facts_written"]
        summary["profiles_updated"] += int(r["profile_updated"])
        if max_people and summary["people_enriched"] >= max_people:
            break
    logger.info(f"person_backfill: uid={uid} {summary}")
    return summary


def maybe_backfill_on_first_sync(uid: str, language: Optional[str] = None) -> Dict[str, int]:
    """Run the whole-roster backfill exactly once per user, the first time messages sync.

    Uses an atomic Redis set-if-absent so concurrent ingests (iMessage + Telegram +
    WhatsApp landing together) don't each kick off a backfill. Returns {} when it was
    already claimed. Heavy — call it from a background task, never inline on the request."""
    key = _BACKFILL_FLAG.format(uid=uid)
    try:
        claimed = redis_db.r.set(key, "1", nx=True)
    except Exception as e:
        logger.warning(f"person_backfill: first-sync flag check failed uid={uid}: {e}")
        return {}
    if not claimed:
        return {}
    logger.info(f"person_backfill: first-sync backfill starting uid={uid}")
    return backfill_people(uid, language=language)
