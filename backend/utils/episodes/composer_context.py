"""Bounded owner background for episode notes; transcript remains the event authority.

Owner ruling 2026-11-15: all account-owned memory attribution/categories are background.
Uses shared chat quality/lock checks; never another account or deleted data.
Retrieval failure or the one overall deadline omits all memories.
"""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any, Mapping, Sequence
from types import SimpleNamespace

from config.episodes import (
    COMPOSER_MEMORY_TOKENS,
    COMPOSER_PROFILE_TOKENS,
    COMPOSER_MEMORY_QUERY_TOKENS,
    COMPOSER_CONTEXT_MAX_READS,
)
from models.knowledge_ledger_policy import is_prompt_memory_visible

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


def bounded_text(text: str, tokens: int, *, encoding: str = 'o200k_base') -> str:
    """Bound actual tokenizer tokens; the offline fallback bounds UTF-8 bytes."""
    try:
        import tiktoken

        encoder = tiktoken.get_encoding(encoding)
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
    return (
        bounded_text(query, COMPOSER_MEMORY_QUERY_TOKENS, encoding='cl100k_base')
        if topics or entities or frequent
        else ''
    )


def _memory_data(memory: Any) -> Mapping[str, Any]:
    # Preserve known attribution for rendering; missing values remain unknown.
    return memory if isinstance(memory, Mapping) else memory.model_dump(exclude_unset=True)


def composer_memory_eligible(memory: Any) -> bool:
    """Owner ruling 2026-11-15: attribution is information, never an admission gate.

    Reuse chat's quality/paywall predicate. Its separate canonical self-profile
    slot predicate is inappropriate for attributed background about other people.
    Account ownership and canonical suppression remain enforced by MemoryService.
    """
    data = _memory_data(memory)
    row = SimpleNamespace(**{'is_locked': False, 'user_review': None, 'invalid_at': None, **data})
    return bool(
        is_prompt_memory_visible(row)
        and not any(data.get(k) for k in ('deleted', 'is_deleted', 'deleted_at'))
        and data.get('source_state') not in {'tombstoned', 'purged'}
        and data.get('status') not in {'tombstoned', 'deleted', 'purged', 'superseded'}
    )


def _memory_label(data: Mapping[str, Any]) -> str:
    fields = [
        ('category', 'category'),
        ('kind', 'kind'),
        ('subject_scope', 'subject'),
        ('subject_attribution', 'attribution'),
    ]
    labels = [f'{label}={getattr(data.get(key), "value", data.get(key)) or "unknown"}' for key, label in fields]
    date = data.get('created_at') or data.get('valid_at') or data.get('updated_at')
    labels.append('date=' + (str(date)[:10] if date else 'unknown'))
    return '; '.join(labels)


def relevant_memories(members: Sequence[Mapping[str, Any]], memories: Sequence[Any], *, uid: str | None = None) -> str:
    """IDF overlap over <=1000 account-owned candidates; at most 20 attributed background rows."""
    topics, entities, frequent = _episode_terms(members)
    query = topics | entities | frequent
    candidates = []
    for memory in list(memories)[:1000]:
        data = _memory_data(memory)
        if (uid and data.get('uid') not in (None, uid)) or not composer_memory_eligible(memory):
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
            ranked.append((-score, index, f'- [{_memory_label(data)}] {bounded_text(content, 700)}'))
    body = '\n'.join(text for _, _, text in sorted(ranked)[:20])
    return bounded_text(body, COMPOSER_MEMORY_TOKENS)


def retrieval_queries(members: Sequence[Mapping[str, Any]]) -> list[str]:
    """At most three deterministic searches; no planning model turn."""
    topics, entities, frequent = _episode_terms(members)
    queries = [retrieval_query(members)]
    if entities:
        queries.append('People and ongoing projects: ' + ', '.join(sorted(entities)))
    if frequent or topics:
        queries.append('Previous context and commitments about: ' + ', '.join(sorted(frequent | topics)))
    return list(
        dict.fromkeys(bounded_text(q, COMPOSER_MEMORY_QUERY_TOKENS, encoding='cl100k_base') for q in queries if q)
    )[:3]


def _search_memories(uid: str, members: Sequence[Mapping[str, Any]], *, budget: Any = None) -> list[Any]:
    # Owner ruling 2026-11-15: search every account-owned category/tier and both
    # storage generations through the same authoritative universal service.
    from database._client import db
    from utils.memory.memory_service import MemoryService

    service = MemoryService(db_client=db)
    found = {}
    for query in retrieval_queries(members):
        if budget is not None:
            budget.check()
        matches = service.search(
            uid,
            query,
            limit=10,
            candidate_limit=10,
            result_filter=composer_memory_eligible,
            vector_only=True,
            owner_summary=True,
            budget=budget,
            single_attempt=True,
        )
        if budget is not None:
            budget.check()
        for match in matches:
            data = _memory_data(match.memory)
            if data.get('uid') not in (None, uid):
                continue
            identity = data.get('id') or data.get('memory_id') or data.get('content')
            found.setdefault(str(identity), match.memory)
    return list(found.values())


def _list_memories(uid: str, budget: Any) -> list[Any]:
    from database._client import db
    from utils.memory.memory_service import MemoryService

    return MemoryService(db_client=db).read(uid, limit=60, budget=budget)


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
    """One eight-second budget for profile, retrieval, hydration and rendering."""
    fallback = json.dumps({'name': owner[:200], 'output_language': language[:100]})

    def load(deadline):
        from utils.episodes import composer_context_io as sources
        from utils.other.list_budget import ListReadBudget

        budget = ListReadBudget(
            deadline_monotonic=deadline, max_documents=COMPOSER_CONTEXT_MAX_READS, strict_documents=True
        )
        profile, goals, people = {}, [], []
        ids = sorted(
            {
                str(s['person_id'])
                for row in members
                for s in row.get('transcript_segments') or []
                if s.get('person_id') and '/' not in str(s['person_id'])
            }
        )[:20]

        def render():
            return owner_block(
                owner=owner, language=language, timezone=timezone, profile=profile, goals=goals, people=people
            )

        for source in ('profile', 'goals', 'people'):
            budget.check()
            try:
                if source == 'profile':
                    profile = {'ai_user_profile': sources.profile(uid, budget)}
                elif source == 'goals':
                    goals = sources.goals(uid, budget)
                elif ids:
                    people = sources.people(uid, ids, budget)
                budget.check()
            except Exception as error:
                budget.check()
                logger.warning('event=episode_context source=%s exception_type=%s', source, type(error).__name__)
                raise
        # Fail-empty on search/hydration errors, including budget exhaustion.
        # Only a successful empty search may use bounded default-visible list intake.
        budget.check()
        try:
            memories = _search_memories(uid, members, budget=budget)
            budget.check()
            if not memories:
                memories = _list_memories(uid, budget)
            budget.check()
            block = relevant_memories(members, memories, uid=uid)
            budget.check()
            return render(), block
        except Exception:
            budget.check()
            raise

    from utils.episodes.composer_default_context import gather_with_defaults

    return gather_with_defaults(uid, members, load, fallback)
