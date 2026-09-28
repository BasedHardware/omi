#!/usr/bin/env python3
"""Read scalar shadow metrics for the isolated dev release-probe identity.

Uses ADC against the dev backend's customer-data Firestore project. This tool
does one document get with a field mask; it cannot read conversation content
or write Firestore data.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import uuid
from typing import Any, Sequence

PROBE_UID = 'omi-release-probe'
DATA_PROJECT = 'based-hardware'
SCALAR_FIELDS = (
    'outcome',
    'latency_seconds',
    'measured_at',
    'audio_seconds',
    'audio_origin_offset_seconds',
    'audio_timeline_v2',
    'coverage',
    'tail_gap_seconds',
    'word_distance',
    'live_word_count',
    'pass_word_count',
    'live_owner_seconds',
    'pass_owner_seconds',
    'live_speakers',
    'pass_speakers',
    'clock_offset_seconds',
    'remap_success_rate',
    'remap_ambiguous_count',
    'remap_safe',
)


def _conversation_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError('conversation id must be a UUID') from error
    if str(parsed) != value:
        raise argparse.ArgumentTypeError('conversation id must be a canonical UUID')
    return value


def read_result(client: Any, uid: str, conversation_id: str) -> dict[str, Any] | None:
    if uid != PROBE_UID:
        raise ValueError('only the isolated release-probe uid is allowed')
    reference = (
        client.collection('users')
        .document(uid)
        .collection('conversations')
        .document(conversation_id)
        .collection('transcription_shadow_results')
        .document('v1')
    )
    snapshot = reference.get(field_paths=list(SCALAR_FIELDS))
    if not snapshot.exists:
        return None
    raw = snapshot.to_dict() or {}
    metrics: dict[str, Any] = {}
    for field in SCALAR_FIELDS:
        value = raw.get(field)
        if isinstance(value, datetime):
            metrics[field] = value.isoformat()
        elif value is None or isinstance(value, (str, int, float, bool)):
            metrics[field] = value
    return metrics


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True, choices=[PROBE_UID])
    parser.add_argument('--conversation-id', required=True, type=_conversation_id)
    args = parser.parse_args(argv)

    from google.cloud import firestore

    try:
        metrics = read_result(firestore.Client(project=DATA_PROJECT), args.uid, args.conversation_id)
    except Exception as error:
        raise SystemExit(f'shadow result read failed ({type(error).__name__})') from None
    print(json.dumps({'conversation_id': args.conversation_id, 'metrics': metrics}, sort_keys=True, allow_nan=False))
    return 0 if metrics is not None else 2


if __name__ == '__main__':
    raise SystemExit(main())
