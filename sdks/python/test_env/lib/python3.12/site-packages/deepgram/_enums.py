from enum import Enum


class LiveTranscriptionEvent(Enum):
    OPEN = 'open'
    CLOSE = 'close'
    TRANSCRIPT_RECEIVED = 'transcript_received'
    ERROR = 'error'

class Caption(Enum):
    SRT = 'srt'
    WEBVTT = 'webvtt'
