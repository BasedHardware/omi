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
        max_items=4,
        description="List of **new** facts. If any",
        default=[],
    )


class MemoriesByTexts(BaseModel):
    facts: List[Memory] = Field(
        description="List of **new** facts. If any",
        default=[],
    )


# Map for converting categories from old to new format
LEGACY_TO_NEW_CATEGORY = {
    'core': MemoryCategory.system,
    'hobbies': MemoryCategory.system,
    'lifestyle': MemoryCategory.system,
    'interests': MemoryCategory.system,
    'work': MemoryCategory.system,
    'skills': MemoryCategory.system,
    'learnings': MemoryCategory.system,
    'habits': MemoryCategory.system,
    'other': MemoryCategory.system,
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


def identify_category_for_memory(memory: str, categories: List) -> str:
    # TODO: this should be structured output!!
    categories_str = ', '.join(categories)
    prompt = f"""
    You are an AI tasked with identifying the category of a fact from a list of predefined categories. 

    Your task is to determine the most relevant category for the given fact. 

    Respond only with the category name.

    The categories are: {categories_str}

    Fact: {memory}
    """
    response = llm_mini.invoke(prompt)
    return response.content
