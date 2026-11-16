"""Product by-id guard shared by readers outside the conversations router.

The supplied reader stays the owning database API, including injected test and
transaction clients. Recordings remain available to explicitly raw pipelines.
"""


def read_product(reader, *args, **kwargs):
    if kwargs.get('field_paths') is not None:
        fields = list(kwargs['field_paths'])
        kwargs['field_paths'] = fields if 'recording' in fields else [*fields, 'recording']
    row = reader(*args, **kwargs)
    return None if row and row.get('recording') else row


def has_recording_pieces(conversation) -> bool:
    """A v3 window plays from its recording pieces (even an empty list while they are pending).

    The Conversation model defaults recording_pieces to None, so ordinary rows written through
    it carry the key with a null value and must stay on the legacy playback path.
    """
    return bool(conversation) and conversation.get('recording_pieces') is not None
