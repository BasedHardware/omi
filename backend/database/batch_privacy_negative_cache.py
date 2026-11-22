"""Process-local NOT_FOUND hints certified by a transaction's WQ26 token.

Never stores snapshots, positive rows, Redis results or authorization decisions.
The token includes the server revision (including nanoseconds), preventing ABA.
Writers rotate it in the same Commit; the reader's token read enrolls that
authority in the transaction conflict set even when a document read is skipped.
"""

from database.privacy_ttl_cache import BoundedTTLCache, is_missing
from database import privacy_check_metrics as metrics

LOOKUPS = BoundedTTLCache()


class _NotFound:
    exists = False

    def to_dict(self):
        return None


_NOT_FOUND = _NotFound()


def read(client, uid, reference, collection, version, live_read, *, shadow, started):
    """Only called after THIS transaction's uncached token read; None fails closed.

    ``started`` precedes the absence read, bounding even a slow authority walk.
    A shadow hit always reads live, counts any newly existing doc as a mismatch,
    and invalidates the hint. No TTL grace exempts a privacy mismatch.
    """
    mode = 'shadow' if shadow else 'enforce'
    if version is None:
        metrics.negative_lookup(collection, mode, 'miss')
        return live_read(reference)
    key = (client, uid, reference.path)
    cached, _age = LOOKUPS.get(key)
    hit = not is_missing(cached) and cached == version
    if hit and not shadow:
        metrics.negative_lookup(collection, mode, 'hit')
        return _NOT_FOUND
    if not hit:
        metrics.negative_lookup(collection, mode, 'miss')
    snapshot = live_read(reference)
    if hit:
        # Qualification counts completed comparisons, never failed live reads.
        metrics.negative_lookup(collection, mode, 'hit')
    if snapshot.exists:
        LOOKUPS.forget(key)
        if hit:
            metrics.negative_lookup(collection, mode, 'mismatch')
    else:
        # Seed only after a real in-process document read, never another memo.
        LOOKUPS.put(key, version, started=started)
    return snapshot
