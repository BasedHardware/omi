#!/usr/bin/env python3
"""Qualify saved real split-worker outputs; never runs inference or cloud reads.

Private manifest: reference_words, identity_table, excluded_spans, snapshot,
unsplit (one unit), cases ([units]); units have offset and payload JSON path.
All clocks are relative to the identical frozen whole crop. Only aggregates
reach stdout. Each case must tile that crop without overlap or missing audio.
"""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import json
import hashlib
import wave
import math
import os
from pathlib import Path
import secrets
import traceback
import sys


def _digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _pcm(path, digest):
    with wave.open(str(path), 'rb') as handle:
        if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (16000, 1, 2):
            raise ValueError('split_requires_canonical_pcm')
        duration = handle.getnframes() / 16000
        own = hashlib.sha256()
        while block := handle.readframes(65536):
            digest.update(block)
            own.update(block)
    return duration, own.hexdigest()


def verify_provenance(manifest):
    """Bind saved inference receipts to actual PCM, offsets and result bytes.

    The receipts must be written when inference completes, never synthesized
    after scoring. They establish cache provenance; they are not a claim that
    hashes alone authenticate an untrusted model runner.
    """
    value = deepcopy(manifest)
    if _digest(value['source_audio']) != value['source_sha256']:
        raise ValueError('frozen_source_hash_mismatch')
    crop_seconds, crop_hash = _pcm(value['crop_audio'], hashlib.sha256())
    if crop_hash != value['crop_pcm_sha256'] or abs(crop_seconds - value['crop_seconds']) > 1 / 16000:
        raise ValueError('frozen_crop_pcm_mismatch')
    config = value['inference_config']
    if not isinstance(config, dict) or not config:
        raise ValueError('frozen_inference_config_required')
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()
    for units in [value['unsplit'], *value['cases']]:
        combined = hashlib.sha256()
        for unit in units:
            duration, audio_hash = _pcm(unit['audio'], combined)
            receipt = json.loads(Path(unit['receipt']).read_text())
            expected = {
                'source_sha256': value['source_sha256'],
                'crop_pcm_sha256': crop_hash,
                'crop_start_seconds': value['crop_start_seconds'],
                'offset': unit['offset'],
                'duration_seconds': duration,
                'input_pcm_sha256': audio_hash,
                'payload_sha256': _digest(unit['payload']),
                'inference_config_sha256': config_hash,
            }
            if not isinstance(receipt, dict) or any(receipt.get(key) != item for key, item in expected.items()):
                raise ValueError('split_inference_receipt_mismatch')
            unit['payload'] = json.loads(Path(unit['payload']).read_text())
            if abs(unit['payload']['audio_seconds'] - duration) > 1 / 16000:
                raise ValueError('split_result_duration_mismatch')
        if combined.hexdigest() != crop_hash:
            raise ValueError('split_pcm_differs_from_frozen_crop')
    return value


def validate_units(units, crop_seconds):
    """Reject denominator drift caused by silently skipping a split or crop."""
    if not units or len(units) > 256:
        raise ValueError('invalid_split_unit_count')
    end = 0.0
    for unit in units:
        offset, duration = unit['offset'], unit['payload']['audio_seconds']
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (offset, duration)):
            raise ValueError('invalid_split_clock')
        if duration <= 0 or abs(offset - end) > 1 / 16000:
            raise ValueError('split_units_must_tile_frozen_crop')
        end = offset + duration
    if abs(end - crop_seconds) > 1 / 16000:
        raise ValueError('split_crop_differs_from_frozen_crop')


def project_units(units, *, snapshot=None, persist=None):
    """Production projection/voice linking with a durable filesystem-only sink.

    This adapter proves identity continuity, not Firestore atomicity (covered
    by emulator tests). Recreate the allocator and decrypt persisted state at
    every part so the test cannot rely on an in-process speaker map.
    """
    from config.policy import ProjectionPolicy
    from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
    from utils.batch_pipeline.projection import build_incoming
    from utils.batch_pipeline.projection_parts import split_result
    from utils.stt.batch_voice_links import (
        arbitrate_linked_owner_claims,
        decode_registry,
        encode_registry,
        link_unit_voices,
        linking_enabled,
    )
    from utils.stt.speaker_identity import ConversationSpeakerIdAllocator

    owner, canonical = 'local-split-evaluation', 'local-split-conversation'
    segments, ciphertext = [], None
    policy = ProjectionPolicy(authoritative_labels=True)
    for index, unit in enumerate(units):
        payload = deepcopy(unit['payload'])
        unit_id = f'local-unit-{index}'
        item = WorkItem(
            unit_id, owner, 1_700_000_000 + unit['offset'], 'local-only', payload['audio_seconds'], Priority.DEEP
        )
        binding = ProjectionBinding(owner, 'local-job', 'local-content', (unit_id,), privacy_generation=0)
        for part, part_payload in split_result(item, payload):
            options = {'policy': policy, 'batch_segment_id': unit_id}
            if snapshot is not None:
                options['naming_snapshot'] = snapshot
            incoming = build_incoming(part, binding, part_payload, **options)
            selected = incoming['transcript_segments']
            allocator = ConversationSpeakerIdAllocator()
            allocator.hydrate(segments)
            evidence = incoming.pop('_batch_voice_evidence', None)
            if evidence is None:
                raise ValueError('projection_requires_voice_evidence_hook')
            registry = link_unit_voices(
                decode_registry(ciphertext, owner),
                evidence,
                selected,
                allocator,
                existing=segments,
                conversation_id=canonical,
                enabled=linking_enabled(),
            )
            for segment in selected:
                allocator.assign(segment)
                offset = part.capture_at - 1_700_000_000
                segment['start'] += offset
                segment['end'] += offset
            segments = arbitrate_linked_owner_claims(segments + selected, {})
            ciphertext = encode_registry(registry, owner)
            if persist:
                persist({'segments': segments, 'registry': ciphertext})
    return segments


def qualify(manifest, *, project=project_units, scorer=None, provenance_verified=False):
    if not provenance_verified:
        return {'split_gate': 'BLOCKED', 'reason': 'split_provenance_unverified'}
    if scorer is None:
        from utils.stt.diarization_eval import score_recording

        scorer = score_recording
    crop = manifest['crop_seconds']
    unsplit = manifest['unsplit']
    validate_units(unsplit, crop)
    cases = manifest['cases']
    if len(unsplit) != 1 or not 2 <= len(cases) <= 32:
        raise ValueError('unsplit_and_multiple_boundary_cases_required')
    truth, identities = manifest['reference_words'], manifest['identity_table']
    excluded = manifest.get('excluded_spans', [])
    frozen = json.dumps([truth, identities, excluded], sort_keys=True)
    baseline = scorer(truth, project(unsplit), identities, excluded_spans=excluded)
    scores, boundary_sets = [], set()
    any_mid_speech = False
    for index, units in enumerate(cases):
        validate_units(units, crop)
        boundaries = tuple(unit['offset'] for unit in units[1:])
        boundary_sets.add(boundaries)
        mid_speech = any(word['start'] < boundary < word['end'] for boundary in boundaries for word in truth)
        any_mid_speech = any_mid_speech or mid_speech
        if len(units) < 2:
            raise ValueError('split_case_requires_multiple_units')
        score = scorer(truth, project(units), identities, excluded_spans=excluded)
        denominators = ('words', 'owner_enrolled_words')
        same = all(score.get(key) == baseline.get(key) for key in denominators)
        left, right = baseline.get('owner_enrolled_accuracy'), score.get('owner_enrolled_accuracy')
        loss = left - right if left is not None and right is not None else None
        scores.append(
            {
                'case': index,
                'mid_speech_boundary': mid_speech,
                'score': score,
                'same_denominator': same,
                'identity_loss_percentage_points': 100 * loss if loss is not None else None,
                'split_gate': (
                    'PASS'
                    if same and loss is not None and loss <= 0.02 + 1e-12 and score.get('engineering_gate') == 'PASS'
                    else 'FAIL'
                ),
            }
        )
    if len(boundary_sets) < 2 or not any_mid_speech:
        raise ValueError('distinct_boundaries_including_mid_speech_required')
    if frozen != json.dumps([truth, identities, excluded], sort_keys=True):
        raise ValueError('frozen_reference_mutated')
    return {
        'unsplit': baseline,
        'splits': scores,
        'split_gate': (
            'PASS'
            if baseline.get('engineering_gate') == 'PASS' and all(case['split_gate'] == 'PASS' for case in scores)
            else 'FAIL'
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    os.environ['ENCRYPTION_SECRET'] = secrets.token_hex(32)
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.output.chmod(0o700)
    log = args.output / 'projection.log'
    descriptor = os.open(log, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as handle, redirect_stdout(handle), redirect_stderr(handle):
            manifest = verify_provenance(json.loads(args.manifest.read_text()))
            snapshot = None
            if manifest.get('snapshot'):
                from utils.stt.batch_naming import NamingSnapshot

                data = json.loads(Path(manifest['snapshot']).read_text())
                snapshot = NamingSnapshot(
                    'local-split-evaluation',
                    0,
                    owner_profile=data.get('owner_profile') or {},
                    people=tuple(data.get('people') or []),
                    named_allowed=data.get('named_allowed') is True,
                    validate=lambda *args: True,
                )
            counter = 0

            def persist(value):
                nonlocal counter
                destination = args.output / f'part-{counter}.json'
                counter += 1
                fd = os.open(destination, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as output:
                    json.dump(value, output, default=str)

            score = qualify(
                manifest,
                project=lambda units: project_units(units, snapshot=snapshot, persist=persist),
                provenance_verified=True,
            )
        print(json.dumps(score))
        return 0 if score['split_gate'] == 'PASS' else 1
    except Exception:
        with log.open('a') as handle:
            traceback.print_exc(file=handle)
        # Exception strings can contain private paths, names, or transcript text.
        print(json.dumps({'split_gate': 'BLOCKED', 'reason': 'split_projection_failed'}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
