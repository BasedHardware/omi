"""Metadata-only fresh delivery cohort; no document or content reads."""


def fresh_committed_counts(client, namespace: str, now: float) -> tuple[int, int]:
    """Two count aggregations over the same closed 10–20 minute commit window."""
    cohort = (
        client.collection(f'{namespace}_results')
        .where('fresh_capture', '==', True)
        .where('committed_at', '>=', now - 1200)
        .where('committed_at', '<=', now - 600)
    )
    total = cohort.count().get(timeout=10, retry=None)[0][0].value
    pending = cohort.where('projection_state', '==', 'pending').count().get(timeout=10, retry=None)[0][0].value
    return int(total), int(pending)
