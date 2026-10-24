"""Bounded metadata contract; never accept arbitrary payloads into diagnostics."""

import json
import math
import re
from collections.abc import Mapping
from typing import Any

FIELD = 'owner_recognition_diagnostics'
MAX_BYTES = 8192
MAX_LIVE_GENERATIONS = 4
MAX_SCOPES = 8
MAX_COUNT = 2**31 - 1
REASONS = frozenset('''other enqueued no_prints unplaced queue_full already_labeled already_mapped missing_speaker
    no_pcm window_outside_buffer segment_shorter_than_minimum no_fresh_audio window_shorter_than_minimum
    stale_generation rejected manual_decision voice_capacity embedding_budget authority_unavailable rejector_tail_reserved
    profile_invalid profile_ineligible profile_missing profile_failed profile_loaded evidence_pending extraction_failed cancelled
    comparison published scores_disabled scores_generated scores_failed flush_failed rollover finalized drain
    disabled batch_authoritative empty_transcript private_cloud_disabled endpoint_unconfigured no_audio no_eligible all_short
    no_vectors global_manifest_ambiguity zero_text_window invalid_text_window uncovered_window
    manifest_unvalidated capture_coverage_hole placement_deadline no_proven_window listing_limit
    inventory_metadata_invalid manifest_inventory_invalid inventory_count_mismatch inventory_pair_mismatch
    blob_missing blob_read_failed blob_decode_failed read_budget decoded_duration_mismatch decoded_overlap
    decoded_coverage_hole embedding_failed resolved partial budget max_embeddings diarizer_unavailable
    capacity_full no_clip clip_too_short chunk_boundary invalid_vector missing_vector failed no_embeddings unaligned_audio
    voice socket both'''.split())
COUNTS = frozenset('''enqueued attempted successful failed comparisons owner_comparisons published scores_generated
    pending_queue pending_tasks eligible short segments embeddable pending cache_hits new_embeddings valid_vectors
    clip_skips embed_failures excluded_id excluded_speaker requested invalid_vectors missing_vectors stale clips
    profile_failures owner_profile_available scores_present budget_voice budget_socket budget_both'''.split())
DURATIONS = frozenset(('pcm_seconds', 'evidence_seconds', 'speech_seconds', 'elapsed_seconds', 'coverage'))
IDS = ('uid', 'conversation', 'socket', 'recording', 'scope')
ENUMS = frozenset(('reason', 'stop', 'status', 'pass', 'scores'))
ENUM_VALUES = REASONS | frozenset(
    ('first', 'late', 'capture', 'unavailable', 'absent', 'present', 'none', 'complete', 'done')
)


def identifier(value):
    # IDs only, bounded and safe for single-line structured logs.
    return re.sub(r'[^A-Za-z0-9_.:@/-]', '_', value[:128]) if isinstance(value, str) else ''


def summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {key: identifier(value.get(key)) for key in IDS if isinstance(value.get(key), str)}
    for key in ('generation', 'sequence', *COUNTS):
        number = value.get(key)
        if isinstance(number, (int, bool)) and number >= 0:
            result[key] = min(int(number), MAX_COUNT)
    for key in DURATIONS:
        number = value.get(key)
        if isinstance(number, (int, float)) and number >= 0 and (isinstance(number, int) or math.isfinite(number)):
            result[key] = round(float(min(number, 1e9)), 3)
    for key in ENUMS:
        if isinstance(value.get(key), str) and value[key] in ENUM_VALUES:
            result[key] = value[key]
    reasons = value.get('reasons')
    if isinstance(reasons, Mapping):
        result['reasons'] = {
            key: min(int(number), MAX_COUNT)
            for key, number in reasons.items()
            if key in REASONS and isinstance(number, (int, bool)) and number >= 0
        }
    scopes = value.get('scopes')
    if isinstance(scopes, list):
        result['scopes'] = [identifier(scope) for scope in scopes[:MAX_SCOPES] if isinstance(scope, str)]
    return result


def normalize(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    live = value.get('live')
    result: dict[str, Any] = {'version': 1}
    if isinstance(live, list):
        result['live'] = [row for item in live[-MAX_LIVE_GENERATIONS:] if (row := summary(item))]
    first = summary(value.get('first_resolver'))
    if first:
        result['first_resolver'] = first
    # No values other than whitelisted metadata; deterministic encoded size bound.
    while len(json.dumps(result, separators=(',', ':')).encode()) > MAX_BYTES and result.get('live'):
        result['live'].pop(0)
    return result if result.get('live') or first else {}


def merge(current: Any, incoming: Any) -> dict[str, Any]:
    current, incoming = normalize(current), normalize(incoming)
    rows = {}
    for row in [*current.get('live', []), *incoming.get('live', [])]:
        key = (row.get('socket', ''), row.get('conversation', ''), row.get('generation', 0))
        if key not in rows or row.get('sequence', 0) >= rows[key].get('sequence', 0):
            rows[key] = row
    return normalize(
        {
            'live': list(rows.values()),
            # First processing diagnosis is immutable across late repair/reprocessing.
            'first_resolver': current.get('first_resolver') or incoming.get('first_resolver'),
        }
    )
