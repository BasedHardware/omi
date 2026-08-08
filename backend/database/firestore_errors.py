"""Firestore error classifiers, re-exported at the persistence boundary.

Code outside ``database/`` that needs to recognize Firestore write errors imports them from
here instead of from ``database._client`` (the client injection point), so the boundary guard
can forbid ``database._client`` imports everywhere but ``database/``.
"""

from ._client import is_document_size_limit_error, is_expired_transaction_error

__all__ = [
    "is_document_size_limit_error",
    "is_expired_transaction_error",
]
