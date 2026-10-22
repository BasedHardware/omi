"""Backend-owned fast topic line (emoji + short title) for a finished conversation.

Desktop clients used to build this prompt themselves and call Anthropic Haiku so a
just-saved conversation would not sit untitled while full processing ran. The prompt,
the model and the output contract now live here, behind ``get_llm('conv_structure')``.
"""

from typing import Any, Optional, cast, Sequence, Mapping
from config.refactor_modes import serving_for
from utils.llm.output_language import resolve_output_language
from utils.llm.notes_language_inputs import in_profile_segments
from utils.llm.notes_short_clip import NOTES_MIN_WORDS
from utils.conversations.deterministic_minimum import first_sentence, truncate_on_word_boundary
from utils.conversations.relevance_rules import transcript_word_count

from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from utils.llm.usage_tracker import Features, track_usage
from .clients import get_llm
import logging

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 4_000


class ConversationTopic(BaseModel):
    emoji: str = Field(description="One emoji that captures the topic", default="")
    title: str = Field(description="Short title, at most 5 words", default="")


_CONVERSATION_TOPIC_PROMPT = """Summarize this conversation as a topic.
Output only structured data matching the format instructions.

RULES:
- emoji: exactly one emoji that vividly reflects the core subject, mood or outcome. Prefer specific over generic.
- title: at most 5 words, no trailing punctuation, no quotes.
- Do not invent participants or topics that are not in the transcript.

TRANSCRIPT:
{transcript}

{format_instructions}
"""


def generate_conversation_topic(
    uid: str,
    transcript: str,
    *,
    conversation_language: str | None = None,
    segments: Sequence[Mapping[str, Any]] | None = None,
) -> Optional[ConversationTopic]:
    """Return-only emoji + short title through get_llm('conv_structure') (OpenRouter Luna).

    Returns an empty topic for an empty transcript and ``None`` when the model call or
    parse fails, so callers can leave the conversation untitled rather than show noise.
    """
    if serving_for('NOTES_PACKET_V2_MODE', uid) and segments is not None:
        transcript = ' '.join(str(segment.get('text') or '') for segment in in_profile_segments(segments))
    text = (transcript or "").strip()
    if not text:
        return ConversationTopic(emoji="", title="")
    if serving_for('NOTES_PACKET_V2_MODE', uid) and transcript_word_count(text) < NOTES_MIN_WORDS:
        return ConversationTopic(emoji='', title=truncate_on_word_boundary(first_sentence(text)))
    text = text[:MAX_TRANSCRIPT_CHARS]

    try:
        parser = PydanticOutputParser(pydantic_object=ConversationTopic)
        prompt = _CONVERSATION_TOPIC_PROMPT.format(
            transcript=text,
            format_instructions=parser.get_format_instructions(),
        )
        if serving_for('NOTES_PACKET_V2_MODE', uid):
            prompt = f'Write the title in {resolve_output_language(uid, conversation_language)}.\n\n' + prompt
        with track_usage(uid, Features.CONVERSATION_STRUCTURE):
            response = get_llm('conv_structure').invoke(prompt)
        try:
            parsed = parser.parse(cast(str, cast(Any, response).content))
        except Exception as e:
            logger.error("Error parsing conversation topic: %s", type(e).__name__)
            return None
    except Exception:
        logger.exception("Error generating conversation topic for uid=%s", uid)
        return None

    emoji = parsed.emoji.strip()
    title = parsed.title.strip()
    return ConversationTopic(emoji=emoji, title=title)
