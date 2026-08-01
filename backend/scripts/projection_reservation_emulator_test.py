#!/usr/bin/env python3
"""Firestore-emulator contention contract for scheduled projection reservations."""

from __future__ import annotations

import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from typing import Any

PROJECT_ID = os.environ.setdefault('GOOGLE_CLOUD_PROJECT', os.environ.get('GCLOUD_PROJECT', 'demo-projections'))
os.environ.setdefault('GCLOUD_PROJECT', PROJECT_ID)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from google.cloud import firestore

from database import projections


def _claim(
    uid: str,
    projection_id: str,
    cadence_key: str,
    attempt_token: str,
    now: datetime,
    barrier: Barrier,
) -> tuple[str, bool]:
    client = firestore.Client(project=PROJECT_ID)
    barrier.wait(timeout=15)
    reserved = projections.reserve_projection_generation(
        uid,
        projection_id,
        cadence_key,
        attempt_token,
        now=now,
        expires_at=now + timedelta(minutes=15),
        firestore_client=client,
    )
    return attempt_token, reserved


def main() -> int:
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        raise RuntimeError('FIRESTORE_EMULATOR_HOST is required; run through Firebase emulators:exec')

    uid = f'projection-reservation-emulator-{uuid.uuid4().hex}'
    projection_id = str(uuid.uuid4())
    cadence_key = '2026-07-29'
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    attempt_tokens = [str(uuid.uuid4()) for _ in range(4)]
    barrier = Barrier(len(attempt_tokens))

    with ThreadPoolExecutor(max_workers=len(attempt_tokens)) as executor:
        futures = [
            executor.submit(
                _claim,
                uid,
                projection_id,
                cadence_key,
                attempt_token,
                now,
                barrier,
            )
            for attempt_token in attempt_tokens
        ]
        results = [future.result(timeout=30) for future in futures]

    winners = [attempt_token for attempt_token, reserved in results if reserved]
    if len(winners) != 1:
        raise AssertionError(f'expected exactly one reservation owner under contention, got {len(winners)}')
    winner = winners[0]

    client: Any = firestore.Client(project=PROJECT_ID)
    reservation_ref = (
        client.collection('users')
        .document(uid)
        .collection(projections.PROJECTION_RESERVATIONS_COLLECTION)
        .document(projection_id)
    )
    reservation = reservation_ref.get().to_dict() or {}
    if reservation.get('attempt_token') != winner or reservation.get('status') != 'reserved':
        raise AssertionError(f'winning reservation was not persisted atomically: {reservation}')

    projection_data = {
        'id': projection_id,
        'image_path': f'{uid}/{projection_id}/{winner}.png',
    }
    losing_token = next(token for token in attempt_tokens if token != winner)
    if projections.finalize_projection_generation(
        uid,
        projection_data,
        losing_token,
        now=now + timedelta(minutes=1),
        firestore_client=client,
    ):
        raise AssertionError('a losing attempt finalized the winning reservation')
    if not projections.finalize_projection_generation(
        uid,
        projection_data,
        winner,
        now=now + timedelta(minutes=1),
        firestore_client=client,
    ):
        raise AssertionError('the current reservation owner could not finalize')

    stored = (
        client.collection('users')
        .document(uid)
        .collection(projections.PROJECTIONS_COLLECTION)
        .document(projection_id)
        .get()
        .to_dict()
    )
    if stored != projection_data:
        raise AssertionError(f'final projection does not match the winning attempt: {stored}')

    print('PASS: Firestore emulator allowed one projection reservation owner and fenced losing finalization')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
