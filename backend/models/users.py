from enum import Enum


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'
    realtime_transcript = 'realtime_transcript'
    memory_created = 'memory_created'
