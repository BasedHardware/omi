"""Bound the local test driver's live and in-flight producer reservations."""


class CaptureRefused(ValueError):
    pass


async def begin_capture(barriers, uid, conversation_id, *, make_barrier):
    if not uid.startswith('synthetic-lifecycle-') or len(barriers) >= 4 or conversation_id in barriers:
        raise CaptureRefused('bounded synthetic captures required')
    barrier = make_barrier(uid)
    # Reserve before the first suspension so concurrent calls see this owner.
    barriers[conversation_id] = barrier
    try:
        await barrier.begin_recording(conversation_id)
        if conversation_id not in barrier.upload_sessions:
            raise RuntimeError('custody token was not persisted')
    except BaseException:
        if barriers.get(conversation_id) is barrier:
            barriers.pop(conversation_id, None)
        raise
    return barrier
