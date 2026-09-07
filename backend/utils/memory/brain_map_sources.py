"""Everything the account knows, as extraction payloads for a Brain Map rebuild.

The Brain Map used to be rebuilt from memories alone. Memories are a thin,
late-arriving distillation: an account with hundreds of conversations can hold
two of them, and the map then shows three dots. A rebuild has to read the
account the way the user thinks of it — the conversations they had, the people
they talk to, the goals they set, and the memories those produced.

Every source becomes one ``{'id', 'content'}`` payload for the knowledge-graph
extractor, so the extractor itself is unchanged. The ``id`` is what the graph
cites as evidence: a memory keeps its own id so canonical assertions and the
desktop inspector keep resolving it; every other source is prefixed so a client
can tell what it is citing without guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

DEFAULT_MEMORY_LIMIT = 500
#: Most recent conversations first. Each one is a separate extraction call, so
#: this is also the LLM budget a rebuild spends on conversations.
DEFAULT_CONVERSATION_LIMIT = 200
CONVERSATION_SOURCE_PREFIX = 'conversation:'
PEOPLE_SOURCE_ID = 'people:directory'
GOALS_SOURCE_ID = 'goals:active'
#: Extraction reads the whole payload in one prompt; a long meeting is cut to
#: its summary plus the opening of its transcript rather than dropped.
MAX_CONVERSATION_CHARS = 4_000
MAX_TRANSCRIPT_CHARS = 2_400

SourcePayload = Dict[str, str]


@dataclass(frozen=True)
class BrainMapSources:
    payloads: List[SourcePayload]
    #: How many of each source made it into ``payloads``; recorded on the
    #: rebuild status so a thin map can be explained rather than guessed at.
    counts: Dict[str, int]


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def _string_list(values: Any, *keys: str) -> List[str]:
    """Readable strings from a list of dicts (first present key wins) or plain strings."""
    if not isinstance(values, list):
        return []
    result: List[str] = []
    for value in values:
        if isinstance(value, str):
            text = _clean(value)
        elif isinstance(value, Mapping):
            text = next((_clean(value.get(key)) for key in keys if _clean(value.get(key))), '')
        else:
            text = ''
        if text:
            result.append(text)
    return result


def conversation_source_text(
    conversation: Mapping[str, Any],
    *,
    max_chars: int = MAX_CONVERSATION_CHARS,
    transcript_chars: int = MAX_TRANSCRIPT_CHARS,
) -> str:
    """One conversation as prose the extractor can read.

    Title, category and overview lead because they are the server's own
    summary and survive truncation; action items and events name the concrete
    things the conversation was about; the transcript comes last and is the
    part that gets cut.
    """
    structured = conversation.get('structured')
    structured = structured if isinstance(structured, Mapping) else {}
    lines: List[str] = []
    title = _clean(structured.get('title'))
    if title:
        lines.append(f"Conversation: {title}")
    category = structured.get('category')
    category_text = _clean(getattr(category, 'value', category))
    if category_text and category_text != 'other':
        lines.append(f"Topic: {category_text}")
    overview = _clean(structured.get('overview'))
    if overview:
        lines.append(f"Summary: {overview}")
    action_items = _string_list(structured.get('action_items'), 'description', 'title')
    if action_items:
        lines.append("Action items: " + '; '.join(action_items))
    events = _string_list(structured.get('events'), 'title', 'description')
    if events:
        lines.append("Events: " + '; '.join(events))
    transcript = ' '.join(_string_list(conversation.get('transcript_segments'), 'text'))
    if transcript:
        if len(transcript) > transcript_chars:
            transcript = transcript[:transcript_chars].rstrip() + '…'
        lines.append(f"Transcript: {transcript}")
    text = '\n'.join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + '…'
    return text


def _conversation_id(conversation: Mapping[str, Any]) -> str:
    return _clean(conversation.get('id'))


def _conversation_is_readable(conversation: Mapping[str, Any]) -> bool:
    # Locked and discarded conversations are not the user's picture of
    # themselves; a deleted one is a tombstone that still has a document. A
    # conversation without the flag at all predates it and is readable.
    return not any(conversation.get(flag) for flag in ('discarded', 'deleted', 'is_locked'))


def build_brain_map_sources(
    *,
    memories: Iterable[Any] = (),
    conversations: Iterable[Mapping[str, Any]] = (),
    people: Iterable[Mapping[str, Any]] = (),
    goals: Iterable[Mapping[str, Any]] = (),
    conversation_limit: int = DEFAULT_CONVERSATION_LIMIT,
) -> BrainMapSources:
    """Turn already-read records into extraction payloads. Pure; no IO."""
    payloads: List[SourcePayload] = []
    counts = {'memories': 0, 'conversations': 0, 'people': 0, 'goals': 0}

    for memory in memories:
        if getattr(memory, 'is_locked', False):
            continue
        content = _clean(getattr(memory, 'content', ''))
        memory_id = _clean(getattr(memory, 'id', ''))
        if not content or not memory_id:
            continue
        payloads.append({'id': memory_id, 'content': content})
        counts['memories'] += 1

    for conversation in conversations:
        if counts['conversations'] >= conversation_limit:
            break
        conversation_id = _conversation_id(conversation)
        if not conversation_id or not _conversation_is_readable(conversation):
            continue
        content = conversation_source_text(conversation)
        if not content:
            continue
        payloads.append({'id': CONVERSATION_SOURCE_PREFIX + conversation_id, 'content': content})
        counts['conversations'] += 1

    names = sorted({_clean(person.get('name')) for person in people if _clean(person.get('name'))})
    if names:
        payloads.append(
            {
                'id': PEOPLE_SOURCE_ID,
                'content': "People the user knows and talks with: " + ', '.join(names) + '.',
            }
        )
        counts['people'] = len(names)

    goal_lines: List[str] = []
    for goal in goals:
        title = _clean(goal.get('title'))
        outcome = _clean(goal.get('desired_outcome'))
        if not title and not outcome:
            continue
        goal_lines.append(title if not outcome or outcome == title else f"{title} — {outcome}")
    if goal_lines:
        payloads.append(
            {
                'id': GOALS_SOURCE_ID,
                'content': "Goals the user is working toward: " + '; '.join(goal_lines) + '.',
            }
        )
        counts['goals'] = len(goal_lines)

    return BrainMapSources(payloads=payloads, counts=counts)


def collect_brain_map_sources(
    uid: str,
    *,
    db_client: Any = None,
    memory_limit: int = DEFAULT_MEMORY_LIMIT,
    conversation_limit: int = DEFAULT_CONVERSATION_LIMIT,
    read_memories: Optional[Callable[[], Sequence[Any]]] = None,
    read_conversations: Optional[Callable[[], Sequence[Mapping[str, Any]]]] = None,
    read_people: Optional[Callable[[], Sequence[Mapping[str, Any]]]] = None,
    read_goals: Optional[Callable[[], Sequence[Mapping[str, Any]]]] = None,
) -> BrainMapSources:
    """Read every source for ``uid`` and build the payloads.

    Readers are injectable so a test can drive the real assembly without a
    Firestore client; the defaults are the production stores.
    """
    if read_memories is None:
        from database._client import get_firestore_client
        from utils.memory.memory_service import MemoryService

        service = MemoryService(db_client=db_client or get_firestore_client())
        read_memories = lambda: service.read(uid, limit=memory_limit)  # noqa: E731
    if read_conversations is None:
        from database import conversations as conversations_db

        # Discarded conversations are filtered here, in `_conversation_is_readable`,
        # not by the store: its `discarded == False` filter also drops every
        # conversation written before the field existed, which on an old account
        # is most of them. Over-read so the discarded, locked and tombstoned rows
        # do not eat the budget.
        read_conversations = lambda: conversations_db.get_conversations(  # noqa: E731
            uid, limit=conversation_limit * 2, include_discarded=True
        )
    if read_people is None:
        from database import users as users_db

        read_people = lambda: users_db.get_people(uid)  # noqa: E731
    if read_goals is None:
        from database import goals as goals_db

        read_goals = lambda: goals_db.get_all_goals(uid)  # noqa: E731

    return build_brain_map_sources(
        memories=read_memories(),
        conversations=read_conversations(),
        people=read_people(),
        goals=read_goals(),
        conversation_limit=conversation_limit,
    )
