"""Remember which embeddings model wrote a vector namespace (ADR-0086, BACKLOG L19).

``validate_vector_dimension`` catches the case where the model's dimension and the store's disagree. It
cannot catch the one that leaves no trace: swapping a model for another of the SAME dimension. The
vectors are the right length and the geometry is different, so they land in the same collection, search
quality degrades, and nothing fails.

Detecting that needs somewhere to remember which model produced the vectors already in a namespace. It
goes in the document store rather than in the vector store itself:

  * it travels through the port, so it works on Firestore and on Mongo alike;
  * it leaves the vector space untouched. The alternative — a marker point with a reserved id inside the
    collection — needs no new storage but must be excluded from EVERY query, and one forgotten filter is
    a spurious result shown to a user (ADR-0086).

**Unknown is not mismatched.** A namespace with no record — which today is all of them — is adopted at
the first successful comparison, with a line saying so. Refusing to serve on a missing record would make
every existing deployment fail its first boot after this ships, over a fact nobody could have recorded.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Top-level collection, one document per namespace. Not under users/: the namespaces are deployment-wide.
STATE_COLLECTION = 'vector_namespace_state'


def _store() -> Any:
    from database.store import get_document_store

    return get_document_store()


def _path(namespace: str) -> str:
    return f'{STATE_COLLECTION}/{namespace}'


def read_namespace_state(namespace: str) -> Optional[Dict[str, Any]]:
    """The recorded ``{model, dim}`` for a namespace, or None when nothing is recorded."""
    stored = _store().get(_path(namespace))
    if stored is None or not getattr(stored, 'exists', False):
        return None
    return dict(stored.data or {})


def record_namespace_state(namespace: str, *, model: str, dim: int) -> None:
    """Record which model (and dimension) owns a namespace. Idempotent, and never raises.

    Called where the collection is created and after an adoption. A failure here must not take down the
    write that triggered it: the state document is a safety net, and a safety net that can break the
    thing it protects is worse than none.
    """
    try:
        _store().set(_path(namespace), {'namespace': namespace, 'model': model, 'dim': int(dim)})
    except Exception as exc:  # pragma: no cover - defensive, see docstring
        logger.warning('could not record the embeddings model for namespace %s: %s', namespace, exc)


def forget_namespace_state(namespace: str) -> None:
    """Drop the record for a namespace that no longer exists.

    The obligation that comes with keeping state: a list that only grows rots into one nobody reads
    (the L32 lesson). Callers that delete a namespace call this.
    """
    try:
        _store().delete(_path(namespace))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning('could not drop the state record for namespace %s: %s', namespace, exc)


def compare_namespace_model(namespace: str, *, model: str, dim: int) -> Optional[str]:
    """Compare the live model against the record. Returns a human-readable problem, or None.

    Adopts the namespace when nothing is recorded, and says so — the adoption is a real decision (it
    asserts that the vectors already in there came from THIS model) and it should be visible in the log
    of the boot that made it.
    """
    recorded = read_namespace_state(namespace)
    if recorded is None:
        record_namespace_state(namespace, model=model, dim=dim)
        logger.info(
            'STARTUP: adopted %s as the embeddings model of record for vector namespace %s (nothing was '
            'recorded before). If that namespace was written by a different model, re-index it.',
            model,
            namespace,
        )
        return None

    recorded_model = str(recorded.get('model') or '')
    if not recorded_model or recorded_model == model:
        return None
    return f'{namespace}: recorded as written by {recorded_model!r}, but the configured model is {model!r}'
