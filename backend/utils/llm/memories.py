from typing import List, Optional, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from database import users as users_db
from models.memories import Memory, MemoryCategory
from models.other import Person
from models.transcript_segment import TranscriptSegment
from database.users import get_user_language_preference
from utils.prompts import extract_memories_prompt, extract_learnings_prompt, extract_memories_text_content_prompt
from utils.llms.memory import get_prompt_memories
from .clients import get_llm
import logging

logger = logging.getLogger(__name__)


def _get_language_instruction(uid: str, language: Optional[str] = None) -> str:
    if language is None:
        language = get_user_language_preference(uid)
    if language and language != 'en':
        return f'You MUST write all extracted memories/learnings in {language}. Do NOT write them in English.'
    return 'Write all extracted memories/learnings in English.'


class Memories(BaseModel):
    facts: List[Memory] = Field(
        min_items=0,
        max_items=2,
        description="List of **new** memories. Maximum 2 per conversation.",
        default=[],
    )


class MemoriesByTexts(BaseModel):
    facts: List[Memory] = Field(
        description="List of **new** facts. If any",
        default=[],
    )


# Map for converting legacy categories to new format
# - system: Facts ABOUT the user (preferences, opinions, realizations, network, projects)
# - interesting: External wisdom/advice FROM others (with attribution) - actionable insights
LEGACY_TO_NEW_CATEGORY = {
    'auto': MemoryCategory.system,
    'core': MemoryCategory.system,
    'hobbies': MemoryCategory.system,
    'lifestyle': MemoryCategory.system,
    'interests': MemoryCategory.system,
    'work': MemoryCategory.system,
    'skills': MemoryCategory.system,
    'habits': MemoryCategory.system,
    'other': MemoryCategory.system,
    'learnings': MemoryCategory.interesting,  # learnings are external insights
}


def new_memories_extractor(
    uid: str,
    segments: List[TranscriptSegment],
    user_name: Optional[str] = None,
    memories_str: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Memory]:
    # print('new_memories_extractor', uid, 'segments', len(segments), user_name, 'len(memories_str)', len(memories_str))
    if user_name is None or memories_str is None:
        user_name, memories_str = get_prompt_memories(uid)

    person_ids = list(set([s.person_id for s in segments if s.person_id]))
    people = [Person(**p) for p in users_db.get_people_by_ids(uid, person_ids)] if person_ids else []
    content = TranscriptSegment.segments_as_string(segments, user_name=user_name, people=people)
    if not content or len(content) < 25:  # less than 5 words, probably nothing
        return []
    # TODO: later, focus a lot on user said things, rn is hard because of speech profile accuracy
    # TODO: include negative facts too? Things the user doesn't like?
    # TODO: make it more strict?

    language_instruction = _get_language_instruction(uid, language)

    try:
        parser = PydanticOutputParser(pydantic_object=Memories)
        chain = extract_memories_prompt | get_llm('memories') | parser
        response: Memories = chain.invoke(
            {
                'user_name': user_name,
                'conversation': content,
                'memories_str': memories_str,
                'language_instruction': language_instruction,
                'format_instructions': parser.get_format_instructions(),
            }
        )

        # Ensure all new memories use the new category format
        for memory in response.facts:
            if isinstance(memory.category, str) and memory.category in LEGACY_TO_NEW_CATEGORY:
                memory.category = LEGACY_TO_NEW_CATEGORY[memory.category]

        return response.facts
    except Exception as e:
        logger.error(f'Error extracting new facts: {e}')
        return []


def extract_memories_from_text(
    uid: str,
    text: str,
    text_source: str,
    user_name: Optional[str] = None,
    memories_str: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Memory]:
    """Extract memories from external integration text sources like email, posts, messages"""
    if user_name is None or memories_str is None:
        user_name, memories_str = get_prompt_memories(uid)

    if not text or len(text) == 0:
        return []

    language_instruction = _get_language_instruction(uid, language)

    try:
        parser = PydanticOutputParser(pydantic_object=MemoriesByTexts)
        chain = extract_memories_text_content_prompt | get_llm('memories') | parser
        response: Memories = chain.invoke(
            {
                'user_name': user_name,
                'text_content': text,
                'text_source': text_source,
                'memories_str': memories_str,
                'language_instruction': language_instruction,
                'format_instructions': parser.get_format_instructions(),
            }
        )

        # Ensure all new memories use the new category format
        for memory in response.facts:
            if isinstance(memory.category, str) and memory.category in LEGACY_TO_NEW_CATEGORY:
                memory.category = LEGACY_TO_NEW_CATEGORY[memory.category]

        return response.facts
    except Exception as e:
        logger.error(f'Error extracting facts from {text_source}: {e}')
        return []


class Learnings(BaseModel):
    result: List[str] = Field(
        min_items=0,
        max_items=2,
        description="List of **new** learnings. If any",
        default=[],
    )


def new_learnings_extractor(
    uid: str,
    segments: List[TranscriptSegment],
    user_name: Optional[str] = None,
    learnings_str: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Memory]:
    if user_name is None or learnings_str is None:
        user_name, memories_str = get_prompt_memories(uid)

    person_ids = list(set([s.person_id for s in segments if s.person_id]))
    people = [Person(**p) for p in users_db.get_people_by_ids(uid, person_ids)] if person_ids else []
    content = TranscriptSegment.segments_as_string(segments, user_name=user_name, people=people)
    if not content or len(content) < 100:
        return []

    language_instruction = _get_language_instruction(uid, language)

    try:
        parser = PydanticOutputParser(pydantic_object=Learnings)
        chain = extract_learnings_prompt | get_llm('learnings') | parser
        response: Learnings = chain.invoke(
            {
                'user_name': user_name,
                'conversation': content,
                'learnings_str': learnings_str,
                'language_instruction': language_instruction,
                'format_instructions': parser.get_format_instructions(),
            }
        )
        return list(map(lambda x: Memory(content=x, category=MemoryCategory.interesting), response.result))
    except Exception as e:
        logger.error(f'Error extracting new facts: {e}')
        return []


def identify_category_for_memory(memory: str) -> MemoryCategory:
    """
    Identify the category for an externally-provided memory.
    Used when memories come from MCP or developer API where we don't know
    if it's a fact about the user (system) or external insight (interesting).

    Args:
        memory: The memory content to categorize

    Returns:
        MemoryCategory.system or MemoryCategory.interesting
    """
    prompt = f"""You are categorizing a memory into one of two categories:

- "system": Facts ABOUT the user - their preferences, opinions, realizations, relationships, projects, personal details
- "interesting": External wisdom/advice FROM others - actionable insights, tips, learnings with attribution

Examples:
- "John prefers morning meetings" → system (fact about John)
- "Sarah's colleague recommended using Notion for project management" → interesting (advice from someone)
- "Lives in San Francisco" → system (personal fact)
- "Naval: read what you love until you love to read" → interesting (wisdom from Naval)
- "Works at Google as a software engineer" → system (career fact)
- "YC tip: talk to users every week" → interesting (advice from YC)

Memory: "{memory}"

Respond with ONLY "system" or "interesting" - nothing else."""

    try:
        response = get_llm('memory_category').invoke(prompt)
        category_str = response.content.strip().lower()
        if category_str == 'interesting':
            return MemoryCategory.interesting
        return MemoryCategory.system
    except Exception as e:
        logger.error(f'Error identifying category for memory: {e}')
        return MemoryCategory.system


class MemoryResolution(BaseModel):
    """Result of resolving a new memory against similar existing memories.

    Drives the "constantly updated brain": when a new fact changes the truth of an
    older one (e.g. loved ice cream -> now hates it, lived in NYC -> now LA, age 25 -> 26),
    the older memory is listed in `supersedes` so it gets invalidated, while the new fact
    is stored as the current truth.
    """

    action: str = Field(
        description=(
            "One of: 'add' (store the new memory; existing facts stay untouched), "
            "'skip' (new is a duplicate / already known — do not store), "
            "'update' (new fact makes one or more existing facts outdated/false — store new AND list them in supersedes), "
            "'merge' (new + existing should become a single richer fact — provide merged_content AND list the ones it replaces in supersedes), "
            "'keep_both' (related but BOTH remain true at the same time — store new, supersede nothing)"
        )
    )
    supersedes: List[int] = Field(
        default=[],
        description=(
            "1-based indices (from the numbered EXISTING list) of memories that are now "
            "OUTDATED or FALSE and must be invalidated. Only for 'update' / 'merge'. "
            "Never include a fact that can still be true alongside the new one."
        ),
    )
    merged_content: Optional[str] = Field(
        default=None, description="If action is 'merge', the combined/refined memory content. Keep under 12 words."
    )
    reasoning: str = Field(default="", description="Brief explanation of why this action was chosen")


# Backwards-compatible action aliases (older callers/tests used these names).
_LEGACY_ACTION_ALIASES = {'keep_new': 'add', 'keep_existing': 'skip'}


def resolve_memory_conflict(
    new_memory: str,
    similar_memories: List[dict],
    language: Optional[str] = None,
) -> MemoryResolution:
    """
    Use an LLM to decide how a newly extracted memory relates to existing similar ones,
    and which (if any) existing memories it makes outdated.

    Args:
        new_memory: The newly extracted memory content
        similar_memories: Ordered list of similar existing memories, each a dict with at
            least 'content' (and usually 'memory_id', 'score'). The 1-based position in
            this list is what `MemoryResolution.supersedes` refers to.
        language: Language code for merged content output

    Returns:
        MemoryResolution with action, supersedes indices, and optional merged content.
    """
    if not similar_memories:
        return MemoryResolution(action='add', reasoning='No similar memories found')

    existing_str = "\n".join(
        [f"{i + 1}. \"{m['content']}\" (similarity: {m.get('score', 0):.2f})" for i, m in enumerate(similar_memories)]
    )

    language_note = ""
    if language and language != 'en':
        language_note = f"\n- If action is 'merge', write merged_content in {language} (same language as the memories)."

    prompt = f"""You maintain a personal knowledge base of true facts about a user. A NEW fact was just learned.
Decide how it relates to the EXISTING facts so the knowledge base always reflects the CURRENT truth.

NEW FACT: "{new_memory}"

EXISTING FACTS (numbered):
{existing_str}

Choose ONE action:
- "add": the new fact is genuinely new and does not change any existing fact. Store it.
- "skip": the new fact is already captured by an existing fact (a duplicate / no new info). Do not store it.
- "update": the new fact makes one or more existing facts OUTDATED or FALSE (the same attribute now has a different value). Store the new fact AND put the indices of every outdated fact in "supersedes".
- "merge": the new fact and an existing one should become a SINGLE richer fact. Provide "merged_content" AND put the replaced indices in "supersedes".
- "keep_both": the new fact and the existing ones are all still TRUE at the same time. Store the new fact, supersede nothing.

CRITICAL — only put a fact in "supersedes" if it is now genuinely FALSE or OUTDATED. Two preferences that can both be true at once must NEVER supersede each other.{language_note}

EXAMPLES:
- New: "Hates ice cream" | Existing: 1."Loves ice cream" → update, supersedes [1] (preference flipped — the old one is now false)
- New: "Lives in Los Angeles" | Existing: 1."Lives in New York City" → update, supersedes [1] (moved — can't live in both)
- New: "Is 26 years old" | Existing: 1."Is 25 years old" → update, supersedes [1] (age changed)
- New: "Works at Google as engineer" | Existing: 1."Works at Google" → merge: "Works at Google as engineer", supersedes [1]
- New: "Enjoys hiking" | Existing: 1."Enjoys hiking" → skip (duplicate)
- New: "Likes tennis" | Existing: 1."Likes basketball" → keep_both (can like both sports)
- New: "Has a dog named Max" | Existing: 1."Has a dog", 2."Lives in NYC" → merge: "Has a dog named Max", supersedes [1]

Respond with action, supersedes (indices), merged_content (only for merge), and reasoning."""

    try:
        parser = PydanticOutputParser(pydantic_object=MemoryResolution)
        chain = get_llm('memory_conflict') | parser
        response: MemoryResolution = chain.invoke(prompt + f"\n\n{parser.get_format_instructions()}")
        response.action = _LEGACY_ACTION_ALIASES.get(response.action, response.action)
        return response
    except Exception as e:
        logger.error(f'Error resolving memory conflict: {e}')
        # Default to storing the new memory if resolution fails (never lose information).
        return MemoryResolution(action='add', reasoning=f'Resolution failed: {e}')
