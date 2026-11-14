"""Bounded owner background for episode notes; transcript remains the event authority.

Uses the chat prompt's default-visible, processed memory intake and its existing
30-second cache. Ranking is local, so context adds no embedding or model call.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence

from config.episodes import COMPOSER_MEMORY_TOKENS, COMPOSER_PROFILE_TOKENS

logger = logging.getLogger(__name__)
_STOP = frozenset(
    (
        'the and for with that this from have about they were will would there their '
        'what when your you are was not but all can has had who how into also just '
        'then than some more one our out its them being been'.split()
    )
)


def bounded_text(text: str, tokens: int) -> str:
    """Bound actual tokenizer tokens; the offline fallback bounds UTF-8 bytes."""
    try:
        import tiktoken

        encoder = tiktoken.get_encoding('o200k_base')
        return encoder.decode(encoder.encode(text, disallowed_special=())[:tokens])
    except Exception:
        return text.encode('utf-8')[:tokens].decode('utf-8', errors='ignore')


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r'[^\W_]+', text.casefold()) if len(t) >= 3 and t not in _STOP}


def relevant_memories(members: Sequence[Mapping[str, Any]], memories: Sequence[Any]) -> str:
    """IDF overlap over <=1000 vetted candidates; retain at most 20 relevant facts."""
    query: set[str] = set()
    for row in members:
        structured = row.get('structured') or {}
        query |= _terms(str(structured.get('title') or '') + ' ' + str(structured.get('overview') or ''))
        # Raw speech provides a fallback when a pending member has no summary yet.
        query |= _terms(' '.join(str(s.get('text') or '') for s in row.get('transcript_segments') or []))
    candidates = []
    for memory in list(memories)[:1000]:
        data = memory if isinstance(memory, Mapping) else memory.model_dump()
        if data.get('is_locked') or data.get('user_review') is False or data.get('invalid_at'):
            continue
        content = str(data.get('content') or '').strip()
        if content:
            candidates.append((data, content, _terms(content)))
    frequency = Counter(term for _, _, terms in candidates for term in terms)
    ranked = []
    for index, (data, content, terms) in enumerate(candidates):
        overlap = query & terms
        score = sum(math.log(1 + len(candidates) / frequency[t]) for t in overlap) / math.sqrt(max(1, len(terms)))
        if score > 0:
            attribution = (
                getattr(data.get('subject_attribution'), 'value', data.get('subject_attribution')) or 'unknown'
            )
            ranked.append((-score, index, f'- [{attribution}] {bounded_text(content, 700)}'))
    body = '\n'.join(text for _, _, text in sorted(ranked)[:20])
    return bounded_text(body, COMPOSER_MEMORY_TOKENS)


def owner_block(
    *,
    owner: str,
    language: str,
    timezone: str,
    profile: Mapping[str, Any],
    goals: Sequence[Mapping[str, Any]],
    people: Sequence[Mapping[str, Any]],
) -> str:
    """Only named profile fields, active goals and people already bound to this speech."""
    ai = profile.get('ai_user_profile') or {}
    data = {
        'name': owner,
        'output_language': language,
        'timezone': timezone,
        'profile': ai.get('profile_text') if isinstance(ai, Mapping) else '',
        'active_goals': [str(g.get('title') or g.get('description') or '')[:500] for g in goals[:5]],
        'known_people_in_transcript': [
            {k: p[k] for k in ('name', 'relationship', 'description') if p.get(k)}
            for p in people[:20]
            if not p.get('is_dismissed')
        ],
    }
    return bounded_text(json.dumps(data, ensure_ascii=False, default=str), COMPOSER_PROFILE_TOKENS)


def gather(
    uid: str, members: Sequence[Mapping[str, Any]], *, owner: str, language: str, timezone: str
) -> tuple[str, str]:
    """Best effort per source; a background lookup failure cannot lose the notes."""
    from database import goals as goals_db, users as users_db
    from utils.llms.memory import get_prompt_data

    profile, goals, people, memories = {}, [], [], []
    for source in ('profile', 'goals', 'people', 'memories'):
        try:
            if source == 'profile':
                profile = {'ai_user_profile': users_db.get_ai_user_profile(uid) or {}}
            elif source == 'goals':
                goals = goals_db.get_user_goals(uid, limit=5)
            elif source == 'people':
                ids = sorted(
                    {
                        str(s['person_id'])
                        for row in members
                        for s in row.get('transcript_segments') or []
                        if s.get('person_id')
                    }
                )[:20]
                people = users_db.get_people_by_ids(uid, ids) if ids else []
            else:
                _, baseline, manual, generated = get_prompt_data(uid)
                memories = [*baseline, *manual, *generated]
        except Exception as error:
            logger.warning('event=episode_context source=%s exception_type=%s', source, type(error).__name__)
    return owner_block(
        owner=owner, language=language, timezone=timezone, profile=profile, goals=goals, people=people
    ), relevant_memories(members, memories)
