import re
import time

from fastapi import APIRouter

from models import *
from db import get_upsert_segment_to_transcript_plugin

router = APIRouter()

scan_segment_session = {}

# *******************************************************
# ************ Basic Mentor Plugin ************
# *******************************************************

@router.post('/mentor', tags=['mentor', 'basic', 'realtime'], response_model=MentorEndpointResponse)
def mentoring(data: RealtimePluginRequest):
    def normalize(text):
        return re.sub(r' +', ' ',re.sub(r'[,?.!]', ' ', text)).lower().strip()

    # Add segments by session_id
    session_id = data.session_id
    segments = get_upsert_segment_to_transcript_plugin('mentor-01', session_id, data.segments)
    scan_segment = scan_segment_session[session_id] if session_id in scan_segment_session and len(segments) > len(data.segments) else 0

    # Detect codewords
    ai_names = ['Omi', 'Omie', 'Homi', 'Homie']
    codewords = [f'hey {ai_name} what do you think' for ai_name in ai_names]
    scan_segments = TranscriptSegment.combine_segments([], segments[scan_segment:])
    if len(scan_segments) == 0:
        return {}
    text_lower = normalize(scan_segments[-1].text)
    pattern = r'\b(?:' + '|'.join(map(re.escape, [normalize(cw) for cw in codewords])) + r')\b'
    if not bool(re.search(pattern, text_lower)):
        return {}

    # Generate mentoring prompt
    scan_segment_session[session_id] = len(segments)
    transcript = TranscriptSegment.segments_as_string(segments)

    user_name = "{{user_name}}"
    user_facts = "{{user_facts}}"

    prompt = f"""
    You are an experienced mentor, that helps people achieve their goals during the meeting.
    You are advising {user_name} right now.

    {user_facts}

    The following is a {user_name}'s conversation, with the transcripts, that {user_name} had during the meeting.
    {user_name} wants to get the call-to-action advice to move faster during the meetting based on the conversation.

    First, identify the topics or problems that {user_name} is discussing or trying to resolve during the meeting, and then provide advice specific to those topics or problems. If you cannot find the topic or problem of the meeting, respond with an empty message.

    The advice must focus on the specific object mentioned in the conversation. The object could be a product, a person, or an event.

    The response must follow this format:
    Noticed you are trying to <meeting topics or problems>.
    If I were you, I'd <actions>.

    Remember {user_name} is busy so this has to be very efficient and concise.
    Respond in at most 100 words.

    Output your response in plain text, without markdown.
    ```
    ${transcript}
    ```
    """.replace('    ', '').strip()

    return {'session_id': data.session_id,
            'mentor': {'prompt': prompt,
                       'params': ['user_name', 'user_facts']}}

@ router.get('/setup/mentor', tags=['mentor'])
def is_setup_completed(uid: str):
    return {'is_setup_completed': True}
