"""Mock models.conversation — minimal Conversation model."""

from enum import Enum


class ConversationStatus(str, Enum):
    processing = 'processing'
    completed = 'completed'
    discarded = 'discarded'


class Geolocation:
    def __init__(self, latitude=0, longitude=0, **kwargs):
        self.latitude = latitude
        self.longitude = longitude


class Conversation:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', 'conv-0')
        self.status = kwargs.get('status', ConversationStatus.processing)
        self.geolocation = None
        self.discarded = False
        # Accept and ignore any other fields
        for k, v in kwargs.items():
            if not hasattr(self, k):
                setattr(self, k, v)
