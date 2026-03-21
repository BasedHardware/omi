from typing import List, Optional

from models.other import Person
from models.transcript_segment import TranscriptSegment
from utils.llm.clients import llm_mini
from utils.llm.usage_tracker import track_usage, Features


def followup_question_prompt(
    uid: str, segments: List[TranscriptSegment], people: Optional[List[Person]] = None, user_name: str = None
):
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
        return llm_mini.invoke(prompt).content
