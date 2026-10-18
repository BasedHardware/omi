"""Firestore transport for private cohorts; all clients remain lazy."""

from typing import Any

from config.rollout_cohorts import COLLECTION, COHORT_ENVS, valid_uid
from database._client import get_data_plane_firestore_client


def read_memberships(uid: str, *, firestore_client: Any | None = None) -> dict[str, dict[str, bool]]:
    client = firestore_client or get_data_plane_firestore_client()
    doc = client.collection(COLLECTION).document(uid).get(timeout=1.0, retry=None)
    if not doc.exists:
        return {}
    data = doc.to_dict()
    members = data.get('cohorts') if isinstance(data, dict) else None
    if not isinstance(members, dict) or any(
        not isinstance(flags, dict) or any(type(value) is not bool for value in flags.values())
        for flags in members.values()
    ):
        raise ValueError('invalid cohort document')
    return members


def read_cohort_members(name: str, *, firestore_client: Any | None = None) -> tuple[str, ...]:
    client = firestore_client or get_data_plane_firestore_client()
    environment, name = name.split(':', 1)
    if environment not in {'prod', 'dev', 'local', 'offline'} or name not in COHORT_ENVS:
        raise ValueError('invalid cohort discovery scope')
    rows = list(
        client.collection(COLLECTION)
        .where(f'cohorts.{environment}.`{name}`', '==', True)
        .limit(500)
        .stream(timeout=1.0, retry=None)
    )
    if len(rows) >= 500:
        raise ValueError('cohort discovery limit exceeded')
    return tuple(row.id for row in rows if valid_uid(row.id))
