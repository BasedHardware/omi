"""Retained record-barrier dead letters: private requeue and aggregate stock.

No audio, conversation, custody or provider operations belong here. The normal
store commit boundary supplies the same privacy fence as record admission.
"""


def requeue_record(store, segment_id, now):
    """CAS only our terminal reason back to admission; usable with expiry off."""

    def commit(tx):
        job = tx.get('jobs', segment_id)
        if job.get('state') != 'dead' or job.get('dead_letter_reason') != 'record_barrier_aged':
            return False
        job.update(
            state='record_pending',
            available_at=now,
            merge_pending=False,
            dead_letter_reason=None,
            record_dead_letter_at=None,
            record_dead_letter_deadline_at=None,
        )
        tx.put('jobs', segment_id, job)
        return True

    return store.run(commit)


def record_dead_letter_stock(client, namespace):
    query = client.collection(f'{namespace}_jobs').where('state', '==', 'dead')
    return (
        query.where('dead_letter_reason', '==', 'record_barrier_aged').count().get(timeout=10, retry=None)[0][0].value
    )
