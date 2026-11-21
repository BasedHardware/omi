"""Operator-only paid result receipt; never releases audio or changes job state."""

from database.batch_pipeline_quarantine_recovery import RecoveryStore


def mark_spent(store, sid, token, intent, now):
    if intent not in {'recovery', 'speech_redrive'}:
        raise ValueError('closed paid intent required')

    def commit(tx):
        job, _ = RecoveryStore(store).checked(tx, sid)
        existing = tx.get('results', sid)
        marker = job.get(intent) or {}
        state = job.get('recovery_state') if intent == 'recovery' else marker.get('state')
        if state != 'running' or marker.get('token') != token or job.get('result') or existing:
            return False
        if marker.get('paid_state') == 'attempted':
            marker.update(paid_state='spent', spent_at=now)
            tx.put('jobs', sid, job)
        return True

    return store.run(commit)
