from typing import List, Optional, cast

from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.llm.clients import get_llm
from utils.llm.usage_tracker import track_usage, Features


def _response_text(response: object) -> str:
    content = getattr(response, 'content', response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in cast(list[object], content):
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                block = cast(dict[str, object], item)
                text = block.get('text') or block.get('content') or ''
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return ''.join(parts)
    return str(content)


def followup_question_prompt(
    uid: str, segments: List[TranscriptSegment], people: Optional[List[Person]] = None, user_name: Optional[str] = None
) -> str:
    transcript_str = TranscriptSegment.segments_as_string(
        segments, include_timestamps=False, people=people, user_name=user_name
    )
    words = transcript_str.split()
    w_count = len(words)
    if w_count < 10:
        return ''
    elif w_count > 100:
        # trim to last 500 words
        transcript_str = ' '.join(words[-100:])

    prompt = f"""
        You will be given the transcript of an in-progress conversation.
        Your task as an engaging, fun, and curious conversationalist, is to suggest the next follow-up question to keep the conversation engaging.

        Conversation Transcript:
        {transcript_str}

        Output your response in plain text, without markdown.
        Output only the question, without context, be concise and straight to the point.
        """.replace('    ', '').strip()
    with track_usage(uid, Features.FOLLOWUP):
        return _response_text(get_llm('followup').invoke(prompt))
