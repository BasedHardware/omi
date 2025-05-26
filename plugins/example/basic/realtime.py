import re

from fastapi import APIRouter

from models import *

router = APIRouter()


# *******************************************************
# ************ On Transcript Received Plugin ************
# *******************************************************

@router.post('/cursing-checker', tags=['basic', 'realtime'], response_model=EndpointResponse)
def cursing_checker(data: RealtimePluginRequest):
    """
    This plugin checks if the transcript contains any curse words.
    Without understanding the whole conversation. Just the new segments obtained.
    """
    curse_words = ['shit', 'fuck', 'bitch', 'bastard']
    transcript = TranscriptSegment.segments_as_string(data.segments)
    text_lower = transcript.lower()
    pattern = r'\b(?:' + '|'.join(map(re.escape, curse_words)) + r')\b'
    if bool(re.search(pattern, text_lower)):
        return {'message': 'Do not curse'}
    return {}
