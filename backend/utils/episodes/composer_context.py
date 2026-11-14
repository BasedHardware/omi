"""Bounded owner background for episode notes; transcript remains the event authority.

Uses chat's authoritative vector-search facade and profile eligibility policy.
An unavailable search falls back to its cached, bounded default-visible intake.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence
from types import SimpleNamespace

from config.episodes import COMPOSER_MEMORY_TOKENS, COMPOSER_PROFILE_TOKENS, COMPOSER_MEMORY_QUERY_TOKENS
from models.knowledge_ledger_policy import is_prompt_memory_eligible

logger = logging.getLogger(__name__)
_STOP = frozenset(
    (
        'the and for with that this from have about they were will would there their '
        'what when your you are was not but all can has had who how into also just '
        'then than some more one our out its them being been '
        'yeah yes okay right actually really think know want need going good well '
        'now here because still something anything everything should could don does '
        'maybe please sure thank thanks let lets hey hello sorry'.split()
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


def named_entities(members: Sequence[Mapping[str, Any]]) -> list[str]:
    """Deterministic name hints, not identity assertions or an LLM entity pass.

    Repeated proper nouns/acronyms in speech outrank a single passing mention.
    Bound speaker/person names are also hints; names never establish who spoke.
    """
    counts: Counter[str] = Counter()
    for row in members:
        for segment in row.get('transcript_segments') or []:
            text = str(segment.get('text') or '')
            for token in re.findall(r"\b[A-Z][\w’'-]+\b", text):
                if token.casefold() not in _STOP and len(token) >= 3:
                    counts[token.casefold()] += 1
            name = segment.get('person_name')
            if name:
                counts.update(_terms(str(name)))
    return [name for name, _ in counts.most_common(30)]


def _episode_terms(members: Sequence[Mapping[str, Any]]) -> tuple[set[str], set[str], set[str]]:
    topics: set[str] = set()
    speech: Counter[str] = Counter()
    for row in members:
        structured = row.get('structured') or {}
        topics |= _terms(str(structured.get('title') or '') + ' ' + str(structured.get('overview') or ''))
        for segment in row.get('transcript_segments') or []:
            speech.update(_terms(str(segment.get('text') or '')))
    # Repetition across turns is a stronger episode topic than one incidental word.
    frequent = {term for term, count in speech.most_common(32) if count >= 2}
    return topics, set(named_entities(members)), frequent


def retrieval_query(members: Sequence[Mapping[str, Any]]) -> str:
    summaries = []
    for row in members:
        structured = row.get('structured') or {}
        summaries.append(str(structured.get('title') or '') + ': ' + str(structured.get('overview') or ''))
    topics, entities, frequent = _episode_terms(members)
    # Names come first so a many-member episode cannot truncate its best identity hints.
    query = (
        'People/projects named in this transcript: '
        + ', '.join(sorted(entities))
        + '\nRecurring discussion topics: '
        + ', '.join(sorted(frequent))
        + '\nMember topics:\n'
        + '\n'.join(summaries)
    )
    return bounded_text(query, COMPOSER_MEMORY_QUERY_TOKENS) if topics or entities or frequent else ''


def relevant_memories(members: Sequence[Mapping[str, Any]], memories: Sequence[Any]) -> str:
    """IDF overlap over <=1000 vetted candidates; retain at most 20 relevant facts."""
    topics, entities, frequent = _episode_terms(members)
    query = topics | entities | frequent
    candidates = []
    for memory in list(memories)[:1000]:
        data = memory if isinstance(memory, Mapping) else memory.model_dump()
        # Use chat's policy, including canonical ledger subject/kind/intent/slot checks.
        row = SimpleNamespace(
            **{'is_locked': False, 'user_review': None, 'invalid_at': None, 'ledger_schema_version': None, **data}
        )
        if not is_prompt_memory_eligible(row):
            continue
        content = str(data.get('content') or '').strip()
        if content:
            candidates.append((data, content, _terms(content)))
    frequency = Counter(term for _, _, terms in candidates for term in terms)
    ranked = []
    for index, (data, content, terms) in enumerate(candidates):
        overlap = query & terms
        # Entity-linked facts first, then explicit member topics, then recurring speech.
        # A single incidental transcript term cannot make a memory relevant anymore.
        score = sum(
            (6 if t in entities else 3 if t in topics else 1) * math.log(1 + len(candidates) / frequency[t])
            for t in overlap
        ) / math.sqrt(max(1, len(terms)))
        if score > 0:
            attribution = (
                getattr(data.get('subject_scope'), 'value', data.get('subject_scope'))
                if data.get('ledger_schema_version')
                else getattr(data.get('subject_attribution'), 'value', data.get('subject_attribution'))
            ) or 'unknown'
            ranked.append((-score, index, f'- [{attribution}] {bounded_text(content, 700)}'))
    body = '\n'.join(text for _, _, text in sorted(ranked)[:20])
    return bounded_text(body, COMPOSER_MEMORY_TOKENS)


def _search_memories(uid: str, members: Sequence[Mapping[str, Any]]) -> list[Any]:
    # Same hydrated, privacy-fenced vector facade as chat's search_memories_tool.
    # Never trust vector metadata as authoritative content or bypass tombstone checks.
    from database._client import db
    from utils.memory.memory_service import MemoryService

    query = retrieval_query(members)
    if not query:
        return []
    matches = MemoryService(db_client=db).search(
        uid,
        query,
        limit=20,
        candidate_limit=60,
        result_filter=is_prompt_memory_eligible,
    )
    return [match.memory for match in matches]


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
                try:
                    memories = _search_memories(uid, members)
                except Exception as error:
                    logger.warning('event=episode_context source=memory_search exception_type=%s', type(error).__name__)
                    from utils.observability.fallback import record_fallback

                    record_fallback(
                        component='conversation_notes',
                        from_mode='episode_memory_search',
                        to_mode='cached_prompt_memories',
                        reason='other',
                        outcome='degraded',
                        log=logger,
                    )
                if not relevant_memories(members, memories):
                    _, baseline, manual, generated = get_prompt_data(uid)
                    memories = [*baseline, *manual, *generated]
        except Exception as error:
            logger.warning('event=episode_context source=%s exception_type=%s', source, type(error).__name__)
    return owner_block(
        owner=owner, language=language, timezone=timezone, profile=profile, goals=goals, people=people
    ), relevant_memories(members, memories)
