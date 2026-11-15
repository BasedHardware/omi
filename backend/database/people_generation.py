"""Cross-request fence for raw People hints; every People mutation must bump it.

The counter and the People write commit atomically, even when the reader lever
is off. No transactional reads are needed: Increment composes with concurrent
writers. update_time also fences deletion/recreation of the metadata document.
"""

from typing import Any

from google.cloud import firestore


def generation_ref(owner_ref: Any) -> Any:
    return owner_ref.collection('people_meta').document('generation')


def bump_people_generation(writer: Any, person_ref: Any) -> None:
    """Stage alongside a People mutation in the SAME transaction/atomic batch."""
    writer.set(generation_ref(person_ref.parent.parent), {'generation': firestore.Increment(1)}, merge=True)


def read_people_generation(db_client: Any, uid: str) -> tuple | None:
    """One document read; unavailable/uninitialized metadata never authorizes reuse."""
    snapshot = generation_ref(db_client.collection('users').document(uid)).get()
    if not snapshot.exists:
        return None
    value = (snapshot.to_dict() or {}).get('generation')
    if type(value) is not int or value < 0:
        return None
    return value, snapshot.update_time


def write_person(db_client: Any, person_ref: Any, operation: str, *args: Any, **kwargs: Any) -> None:
    """Convert a standalone mutation to an atomic People+generation commit."""

    @firestore.transactional
    def apply(transaction):
        getattr(transaction, operation)(person_ref, *args, **kwargs)
        bump_people_generation(transaction, person_ref)

    apply(db_client.transaction())
