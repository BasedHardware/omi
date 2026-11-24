"""Single-document optimistic CAS shared by lightweight durable obligations."""

import random
import time


def mutate(ref, operation):
    from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound
    from google.cloud import firestore

    for attempt in range(10):
        snapshot = ref.get()
        old = snapshot.to_dict() if snapshot.exists else None
        new, result = operation(old)
        if new == old:
            return result
        try:
            if old is None:
                ref.create(new)
            else:
                removed = {key: firestore.DELETE_FIELD for key in old if key not in new}
                ref.update({**new, **removed}, option=firestore.LastUpdateOption(snapshot.update_time))
            return result
        except (AlreadyExists, FailedPrecondition, NotFound):
            if attempt == 9:
                raise
            time.sleep(random.uniform(0.005, min(0.2, 0.01 * 2**attempt)))
    raise AssertionError('outbox CAS retry budget exhausted')
