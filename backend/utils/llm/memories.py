from typing import List, Optional, Tuple

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from database import users as users_db
from models.memories import Memory, MemoryCategory
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.prompts import extract_memories_prompt, extract_learnings_prompt, extract_memories_text_content_prompt
from utils.llms.memory import get_prompt_memories
from .clients import llm_mini, llm_high


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
    uid: str, segments: List[TranscriptSegment], user_name: Optional[str] = None, memories_str: Optional[str] = None
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

    try:
        parser = PydanticOutputParser(pydantic_object=Memories)
        chain = extract_memories_prompt | llm_mini | parser
        # with_parser = llm_mini.with_structured_output(Facts)
        response: Memories = chain.invoke(
            {
                'user_name': user_name,
                'conversation': content,
                'memories_str': memories_str,
                'format_instructions': parser.get_format_instructions(),
            }
        )

        # Ensure all new memories use the new category format
        for memory in response.facts:
            if isinstance(memory.category, str) and memory.category in LEGACY_TO_NEW_CATEGORY:
                memory.category = LEGACY_TO_NEW_CATEGORY[memory.category]

        return response.facts
    except Exception as e:
        print(f'Error extracting new facts: {e}')
        return []


def extract_memories_from_text(
    uid: str, text: str, text_source: str, user_name: Optional[str] = None, memories_str: Optional[str] = None
) -> List[Memory]:
    """Extract memories from external integration text sources like email, posts, messages"""
    if user_name is None or memories_str is None:
        user_name, memories_str = get_prompt_memories(uid)

    if not text or len(text) == 0:
        return []

    try:
        parser = PydanticOutputParser(pydantic_object=MemoriesByTexts)
        chain = extract_memories_text_content_prompt | llm_mini | parser
        response: Memories = chain.invoke(
            {
                'user_name': user_name,
                'text_content': text,
                'text_source': text_source,
                'memories_str': memories_str,
                'format_instructions': parser.get_format_instructions(),
            }
        )

        # Ensure all new memories use the new category format
        for memory in response.facts:
            if isinstance(memory.category, str) and memory.category in LEGACY_TO_NEW_CATEGORY:
                memory.category = LEGACY_TO_NEW_CATEGORY[memory.category]

        return response.facts
    except Exception as e:
        print(f'Error extracting facts from {text_source}: {e}')
        return []


class Learnings(BaseModel):
    result: List[str] = Field(
        min_items=0,
        max_items=2,
        description="List of **new** learnings. If any",
        default=[],
    )


def new_learnings_extractor(
    uid: str, segments: List[TranscriptSegment], user_name: Optional[str] = None, learnings_str: Optional[str] = None
) -> List[Memory]:
    if user_name is None or learnings_str is None:
        user_name, memories_str = get_prompt_memories(uid)

    person_ids = list(set([s.person_id for s in segments if s.person_id]))
    people = [Person(**p) for p in users_db.get_people_by_ids(uid, person_ids)] if person_ids else []
    content = TranscriptSegment.segments_as_string(segments, user_name=user_name, people=people)
    if not content or len(content) < 100:
        return []

    try:
        parser = PydanticOutputParser(pydantic_object=Learnings)
        chain = extract_learnings_prompt | llm_high | parser
        response: Learnings = chain.invoke(
            {
                'user_name': user_name,
                'conversation': content,
                'learnings_str': learnings_str,
                'format_instructions': parser.get_format_instructions(),
            }
        )
        return list(map(lambda x: Memory(content=x, category=MemoryCategory.interesting), response.result))
    except Exception as e:
        print(f'Error extracting new facts: {e}')
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
        response = llm_mini.invoke(prompt)
        category_str = response.content.strip().lower()
        if category_str == 'interesting':
            return MemoryCategory.interesting
        return MemoryCategory.system
    except Exception as e:
        print(f'Error identifying category for memory: {e}')
        return MemoryCategory.system


class MemoryResolution(BaseModel):
    """Result of resolving a new memory against similar existing memories."""

    action: str = Field(
        description="Action to take: 'keep_new' (add new memory), 'keep_existing' (skip new, existing is sufficient), 'merge' (replace existing with merged version), 'keep_both' (both provide distinct value)"
    )
    merged_content: Optional[str] = Field(
        default=None, description="If action is 'merge', the combined/refined memory content. Must be under 10 words."
    )
    reasoning: str = Field(description="Brief explanation of why this action was chosen")


def resolve_memory_conflict(
    new_memory: str,
    similar_memories: List[dict],
) -> MemoryResolution:
    """
    Use LLM to decide how to handle a new memory that's similar to existing ones.

    Args:
        new_memory: The newly extracted memory content
        similar_memories: List of similar existing memories with 'content' and 'score' keys

    Returns:
        MemoryResolution with action and optional merged content
    """
    if not similar_memories:
        return MemoryResolution(action='keep_new', reasoning='No similar memories found')

    existing_str = "\n".join([f"- \"{m['content']}\" (similarity: {m['score']:.2f})" for m in similar_memories])

    prompt = f"""You are a memory management system. A new memory has been extracted that is similar to existing memories.
Decide the best action to maintain an accurate, non-redundant knowledge base.

NEW MEMORY: "{new_memory}"

SIMILAR EXISTING MEMORIES:
{existing_str}

RULES:
1. "keep_new" - The new memory adds genuinely NEW information not in existing memories
2. "keep_existing" - The new memory is redundant; existing memories already capture this
3. "merge" - The new memory REFINES or UPDATES existing knowledge (e.g., adds specificity, corrects, or combines info). Provide merged_content (max 10 words)
4. "keep_both" - Both memories provide distinct, non-conflicting value (rare - only if truly different aspects)

EXAMPLES:
- Existing: "Likes pancakes" + New: "Doesn't like blueberry pancakes" → merge: "Likes pancakes but not blueberry ones"
- Existing: "Works at Google" + New: "Works at Google as engineer" → merge: "Works at Google as engineer"
- Existing: "Has a dog" + New: "Has a dog named Max" → merge: "Has a dog named Max"
- Existing: "Enjoys hiking" + New: "Enjoys hiking" → keep_existing (duplicate)
- Existing: "Lives in NYC" + New: "Has apartment in Brooklyn" → keep_both (complementary info)

Respond with the action and reasoning."""

    try:
        parser = PydanticOutputParser(pydantic_object=MemoryResolution)
        chain = llm_mini | parser
        response: MemoryResolution = chain.invoke(prompt + f"\n\n{parser.get_format_instructions()}")
        return response
    except Exception as e:
        print(f'Error resolving memory conflict: {e}')
        # Default to keeping new if resolution fails
        return MemoryResolution(action='keep_new', reasoning=f'Resolution failed: {e}')
