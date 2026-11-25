"""Original staged-unit evidence for the existing sync-on batch linker.

Reconstruct projection membership on the pinned result clock, never on rebased
playback offsets. Per-label extraction replaces the sentence extraction path.
Only the existing encrypted conversation cache is written; no enrollment,
retention extension, whole-pass diarization or transcription is performed.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from config.batch_conversation_speakers import batch_unit_scope, vendor_evidence_refused
from utils.batch_pipeline import voice_centroids
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.conversations.speaker_resolution_inputs import batch_provider_keys
from utils.speaker_tag_prompts.clips import pcm_to_wav
from utils.observability.owner_recognition_diagnostics import batch_embedding


@dataclass
class BatchEvidence:
    vectors: dict
    seconds: dict
    validate: Callable[[], None]
    attempted: int = 0
    successful: int = 0
    cache_hits: int = 0
    word_seconds: dict = field(default_factory=dict)


def load(uid, conversation, deadline, *, cache, clip_seconds, extract, max_attempts, reason):
    # Import only on this admitted path; reconstruction is shared with the
    # final pass, but its GPU runner, budget reservation and admission are not.
    from utils.conversations import final_pass_batch as batch

    keys = batch_provider_keys(conversation.transcript_segments)
    units = sorted(
        {
            scope.removeprefix('final:batch:')
            for s in conversation.transcript_segments
            if (scope := batch_unit_scope(s)) and not vendor_evidence_refused(s)
        }
    )
    if len(units) > batch.MAX_UNITS:
        raise OverflowError('unit limit')
    budget = ArtifactReadBudget(deadline, 128 * 1024 * 1024, batch.MAX_UNITS * 2)
    store = batch.FirestoreStore(f'batch_pipeline_{batch.current_stage()}')
    artifacts = batch.artifacts_for(store)
    diagnostics = {}
    failure = batch.UnitFailureContext()
    references = batch.read_unit_references(store, uid, conversation, units, budget, diagnostics, failure)
    if any(not reference[2].private_cloud_sync_enabled for reference in references.values()):
        reason('private_cloud_disabled')
        raise PermissionError('source privacy forbids durable identity evidence')
    # Whole-unit sharing, erasure, expiry and receipt ownership refusals are
    # intentionally identical to the established reconstruction contract.
    checks = []
    result = BatchEvidence({}, {}, lambda: None)
    active_cache_keys = set()
    original_turns = {}
    used_windows = []
    segments = {s.id: s for s in conversation.transcript_segments}
    try:
        for item, pcm, words, validate in batch.decode_unit_evidence(
            uid,
            conversation,
            references,
            store,
            artifacts,
            budget,
            deadline,
            diagnostics,
            failure,
            identity_turns=original_turns,
        ):
            if not validate():
                raise PermissionError('batch evidence changed')
            checks.append(validate)
            unit = item.segment_id
            reference = references[unit]
            # Includes pinned audio/result URIs, privacy generation, projection
            # binding and policy. A replaced result can never reuse an old vector.
            binding_key = hashlib.sha256(repr(reference).encode()).hexdigest()
            by_label = {}
            for word in words:
                sid = word['segment_id']
                segment = segments.get(sid)
                if (
                    segment is None
                    or sid not in keys
                    or segment.speaker_match_source == 'batch_abstention'
                    or vendor_evidence_refused(segment)
                    or segment.end <= segment.start
                ):
                    continue
                label = word['projection_speaker'][1]
                by_label.setdefault(label, []).append(word)
            by_label = {
                label: local
                for label, local in by_label.items()
                if any(segments[w['segment_id']].end - segments[w['segment_id']].start >= 1 for w in local)
            }
            hits = {}
            for label, local in by_label.items():
                # Membership/text qualification occurred in the shared decoder.
                # Limit the clip to current, proven words, excluding donor text.
                geometry = sorted((w['segment_id'], tuple(w['timestamp'])) for w in local)
                key = 'batch-unit:' + hashlib.sha256(repr((binding_key, label, geometry)).encode()).hexdigest()
                cached = cache.get(key)
                seconds = clip_seconds.get(key, 0)
                if (
                    cached is not None
                    and np.asarray(cached[1]).size == voice_centroids.DIMENSION
                    and np.isfinite(cached[1]).all()
                    and 0 < seconds <= voice_centroids.MAX_CLIP_SECONDS
                ):
                    hits[label] = (cached[1], seconds)
                    result.cache_hits += 1
                    batch_embedding('cached')
                by_label[label] = (local, key)
                active_cache_keys.add(key)
            measured_windows = {}
            if by_label:
                # Include all labels when subtracting overlap, even cached labels.
                all_turns = []
                for turn in original_turns[unit]:
                    label = turn['speaker']
                    # Every other original label remains an overlap veto,
                    # including a label without eligible current words.
                    if label not in by_label:
                        all_turns.append(turn)
                        continue
                    for word in by_label[label][0]:
                        low = max(turn['start'], word['timestamp'][0])
                        high = min(turn['end'], word['timestamp'][1])
                        if high > low:
                            all_turns.append(dict(speaker=label, start=low, end=high))

                def embed(clip):
                    if result.attempted >= max_attempts or time.monotonic() >= deadline:
                        raise TimeoutError('batch identity embedding budget')
                    result.attempted += 1
                    batch_embedding('attempted')
                    vector = extract(
                        clip, 'batch_voice.wav', timeout=min(10, deadline - time.monotonic()), use_cache=False
                    )
                    result.successful += 1
                    batch_embedding('successful')
                    return vector

                # The extractor must skip cached labels, while retaining their
                # intervals as overlap exclusions. No extra model pass for a hit.
                missing = [label for label in by_label if label not in hits]
                allowed = set(missing[: max(0, max_attempts - result.attempted)])
                payload = voice_centroids.extract(
                    pcm_to_wav(pcm),
                    all_turns,
                    item.capture_at,
                    embed,
                    execution_deadline=deadline,
                    exclude_labels={turn['speaker'] for turn in all_turns} - allowed,
                    measured_windows=measured_windows,
                )
                for row in payload['labels']:
                    label = row['label']
                    vector = np.asarray(row['vector'], dtype=np.float32)
                    seconds = row['seconds']
                    hits[label] = (vector, seconds)
                    key = by_label[label][1]
                    cache[key] = (seconds, vector)
                    clip_seconds[key] = seconds
            del pcm
            for label, (vector, seconds) in hits.items():
                # Capture-clock union prevents live/WAL duplicates or
                # overlapping original units from multiplying the 5s floor.
                fresh_seconds = 0.0
                for low, high in measured_windows.get(label, []):
                    fresh = [(low, high)]
                    for used_low, used_high in used_windows:
                        fresh = [
                            part
                            for a, b in fresh
                            for part in ((a, min(b, used_low)), (max(a, used_high), b))
                            if part[1] > part[0]
                        ]
                    fresh_seconds += sum(b - a for a, b in fresh)
                    used_windows.append((low, high))
                seconds = min(seconds, fresh_seconds)
                local = by_label[label][0]
                for sid in dict.fromkeys(w['segment_id'] for w in local):
                    spans = sorted(tuple(w['timestamp']) for w in local if w['segment_id'] == sid)
                    union = []
                    for low, high in spans:
                        if union and low <= union[-1][1]:
                            union[-1] = (union[-1][0], max(high, union[-1][1]))
                        else:
                            union.append((low, high))
                    result.word_seconds[sid] = sum(high - low for low, high in union)
                # Each unique clip contributes measured evidence once per unit
                # label, even when the label supplies many sentence vectors.
                for sid in dict.fromkeys(w['segment_id'] for w in local):
                    segment = segments[sid]
                    if segment.end - segment.start < 1:
                        continue
                    result.vectors[sid] = vector
                    assigned = min(seconds, segment.end - segment.start)
                    result.seconds[sid] = assigned
                    seconds -= assigned
            for refusal in set(diagnostics.values()):
                reason(refusal)
    except (ArtifactReadLimit, TimeoutError):
        # A bounded partial result can still qualify earlier proven units.
        # No retry or playback extraction is added within this invocation.
        reason('read_budget')

    def revalidate():
        for check in checks:
            if not check():
                raise PermissionError('batch evidence changed')

    revalidate()
    for key in list(cache):
        if key not in active_cache_keys:
            cache.pop(key)
    result.validate = revalidate
    return result
