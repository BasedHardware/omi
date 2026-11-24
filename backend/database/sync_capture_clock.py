"""Immutable future-clock offsets in the existing sync-assignment metadata."""

import math
from typing import Any

from firebase_admin import auth
from google.cloud import firestore

from database._client import get_firestore_client


class CaptureClockRangeError(ValueError):
    """The fixed mapping would place source audio before its owner's account."""


def account_created_at(uid: str) -> float:
    value = auth.get_user(uid).user_metadata.creation_timestamp
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('account creation time unavailable')
    return value / 1000


def frozen_offset(
    uid: str,
    scope: str,
    raw_end: float,
    received_at: float,
    *,
    raw_start: float,
    lower_bound: float,
    firestore_client: Any = None,
) -> float:
    client = firestore_client or get_firestore_client()
    ref = client.collection('users').document(uid).collection('sync_assignment').document(f'capture-clock-{scope}')

    @firestore.transactional
    def anchor(transaction):
        row = ref.get(transaction=transaction).to_dict()
        if row is not None:
            offset = row.get('offset')
            if row.get('version') != 1 or type(offset) not in (int, float) or not math.isfinite(offset):
                raise ValueError('invalid retained capture-clock anchor')
        else:
            offset = raw_end - received_at
        if raw_start - offset < lower_bound:
            raise CaptureClockRangeError('mapped capture predates account')
        if row is None:
            transaction.set(ref, {'version': 1, 'offset': offset, 'raw_end': raw_end, 'received_at': received_at})
        return float(offset)

    return anchor(client.transaction())


def retained_offsets(uid: str, scopes: list[str]) -> dict[str, float]:
    """Read immutable provenance before a source's filename can appear ordinary."""
    if not scopes:
        return {}
    client = get_firestore_client()
    collection = client.collection('users').document(uid).collection('sync_assignment')
    refs = [collection.document(f'capture-clock-{scope}') for scope in set(scopes)]
    offsets = {}
    # One bounded BatchGet for the upload, including missing-document snapshots.
    for snapshot in client.get_all(refs):
        row = snapshot.to_dict()
        if row is None:
            continue
        offset = row.get('offset')
        if row.get('version') != 1 or type(offset) not in (int, float) or not math.isfinite(offset):
            raise ValueError('invalid retained capture-clock anchor')
        offsets[snapshot.reference.id.removeprefix('capture-clock-')] = float(offset)
    return offsets
