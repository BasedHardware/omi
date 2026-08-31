"""Firestore sentinel values and field transforms, re-exported at the persistence boundary.

Code outside ``database/`` must import sentinels from here
(``from database.sentinels import DELETE_FIELD``) instead of importing the Firestore SDK
directly. This keeps ``google.cloud.firestore`` / ``firebase_admin.firestore`` imports confined
to ``database/`` so the persistence-boundary guard can forbid them everywhere else.
"""

from google.cloud.firestore_v1 import (
    DELETE_FIELD,
    SERVER_TIMESTAMP,
    ArrayRemove,
    ArrayUnion,
    Increment,
    Query,
)

__all__ = [
    "DELETE_FIELD",
    "SERVER_TIMESTAMP",
    "ArrayRemove",
    "ArrayUnion",
    "Increment",
    "Query",
]
