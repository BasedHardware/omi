"""Mock database.conversations — returns minimal valid data with realistic delays."""

import time


def get_conversation(uid, conversation_id):
    """Return a minimal conversation dict that Conversation(**data) will accept."""
    return {
        'id': conversation_id,
        'created_at': '2025-01-01T00:00:00Z',
        'started_at': '2025-01-01T00:00:00Z',
        'finished_at': '2025-01-01T00:01:00Z',
        'status': 'processing',
        'transcript_segments': [],
        'photos': [],
    }


def update_conversation_status(uid, conversation_id, status):
    pass


def set_conversation_as_discarded(uid, conversation_id):
    pass


def create_audio_files_from_chunks(uid, conversation_id):
    return []


def update_conversation(uid, conversation_id, data):
    pass
