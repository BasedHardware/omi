"""High-recall extractor of durable facts ABOUT a person from a messaging thread.

Mirrors `utils.llm.memories.new_memories_extractor` in structure, but:
- uses a HighRecall pydantic parser (uncapped `facts: List[Memory]`), and
- uses the messaging-tuned `extract_person_messaging_memories_prompt`, which pulls durable
  facts about the OTHER person in the thread (their plans/work/relationships/preferences/
  life events/location), skipping logistics and chit-chat.

The transcript is UNTRUSTED contact-generated content: it is HTML-escaped (`_fence`) before
it is rendered into the (single, human-message) prompt, and the prompt itself instructs the
model to treat that block as literal data, never as instructions. Contact text never lands
in a system prompt.
"""

import html
import logging
from typing import List, Optional

from langchain_core.output_parsers import PydanticOutputParser

from database import users as users_db
from models.memories import Memory
from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.llm.memories import HighRecallMemories, LEGACY_TO_NEW_CATEGORY, _get_language_instruction
from utils.llms.memory import get_prompt_memories
from utils.prompts import extract_person_messaging_memories_prompt
from .clients import get_llm

logger = logging.getLogger(__name__)

# Minimum rendered-transcript length before we bother the LLM (mirrors new_memories_extractor).
_MIN_TRANSCRIPT_CHARS = 25


def _fence(text: Optional[str]) -> str:
    """Escape untrusted content before it is interpolated into the prompt.

    Contact messages/names could otherwise carry markup that forges a delimiter or
    injects instructions. HTML-escaping ``&<>`` keeps the text readable to the model
    while making it impossible to break out of the transcript block."""
    return html.escape(str(text) if text else '', quote=False)


def extract_person_messaging_memories(
    uid: str,
    person_name: str,
    segments: List[TranscriptSegment],
    user_name: Optional[str] = None,
    memories_str: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Memory]:
    """Extract durable facts ABOUT ``person_name`` from a messaging thread.

    Args:
        uid: Owning user id.
        person_name: Display name of the person the facts are about (the OTHER party).
        segments: Full transcript segments of the conversation (context).
        user_name: The user's name (for transcript rendering). Fetched if None.
        memories_str: Existing facts already known about this person, to avoid repeating.
            Defaults to '' when None (caller is expected to pass the person's facts).
        language: Language code for the extracted facts.

    Returns:
        List of `Memory` (uncapped, high recall). `[]` on empty/short input or any error.
    """
    if user_name is None:
        user_name, _ = get_prompt_memories(uid)
    if memories_str is None:
        memories_str = ''

    person_ids = list({s.person_id for s in segments if s.person_id})
    people = [Person(**p) for p in users_db.get_people_by_ids(uid, person_ids)] if person_ids else []
    content = TranscriptSegment.segments_as_string(segments, user_name=user_name, people=people)
    if not content or len(content) < _MIN_TRANSCRIPT_CHARS:
        return []

    language_instruction = _get_language_instruction(uid, language)

    try:
        parser = PydanticOutputParser(pydantic_object=HighRecallMemories)
        chain = extract_person_messaging_memories_prompt | get_llm('memories') | parser
        response: HighRecallMemories = chain.invoke(
            {
                'user_name': _fence(user_name),
                'person_name': _fence(person_name),
                'conversation': _fence(content),
                'memories_str': memories_str,
                'language_instruction': language_instruction,
                'format_instructions': parser.get_format_instructions(),
            }
        )

        memories = response.facts or []
        # Normalize any legacy category strings the model may emit.
        for memory in memories:
            if isinstance(memory.category, str) and memory.category in LEGACY_TO_NEW_CATEGORY:
                memory.category = LEGACY_TO_NEW_CATEGORY[memory.category]

        return memories
    except Exception as e:
        logger.error(f'Error extracting person messaging memories for uid={uid}: {e}')
        return []
