"""CPU-only audio proof for auto-language native records, before encrypted staging.

The learned profile admits capture custody, never a Parakeet route. Every 30 s
of audio must pass both independent classifiers. Refusal freezes
``und`` for the unchanged worker barrier and fenced multilingual recovery.
"""

import json

from config.audio_archive import derived_audio_bucket
from config.server_batch import AUTO_LANGUAGES
from config.stt_provider_policy import normalized_stt_language
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.batch_pipeline.language_probe_authorization import ServingLanguageProbeGuard
from utils.batch_pipeline.recovery_disposition import inspect_audio
from utils.batch_pipeline.source_audio import MAGIC, materialize, read_reference
from utils.other.storage import private_cloud_sync_bucket
from utils.stt import batch_language, language_gate
from utils.executors import db_executor, storage_executor, sync_executor, record_language_executor, run_blocking


def classify_probe(probe, guard):
    """One bounded pair of network calls, on the isolated language pool."""
    vendor = batch_language.detect(probe, before_probe=guard)
    guard.raise_if_denied()
    if not vendor.parakeet_safe or vendor.evidence != 'audio_lid':
        return None
    if not guard():
        guard.raise_if_denied()
        return None
    verdict = language_gate.self_detect(probe, surface='batch')
    _, seconds = batch_language.probe_wav(probe)
    if verdict is None or abs(verdict.audio_seconds - seconds) > 0.1 or not verdict.parakeet:
        return None
    return vendor


async def classify_wav(item, wav, guard):
    """Whole unit, no first-window inheritance; no ASR text or primary-language hint."""
    pcm, _, spans = await run_blocking(sync_executor, inspect_audio, item, wav)
    refused = {'stt_language': 'und', 'stt_language_evidence': 'unavailable', 'stt_language_confidence': 0.0}
    if not spans:
        return refused  # The worker owns the independent silence disposition.
    language, confidence, windows = None, 1.0, 0
    step = 30 * 32000
    # Scan the original timeline, including gaps and speech strict VAD missed.
    # The worker's model VAD may hear speech outside the strict CPU spans.
    for offset in range(0, len(pcm), step):
        # Overlap the final short tail, so it is not classified out of context.
        start = max(0, min(offset, len(pcm) - step))
        probe = audio_unit(0, pcm[start : start + step]).wav
        vendor = await run_blocking(record_language_executor, classify_probe, probe, guard)
        if vendor is None:
            return refused
        language = language or vendor.language
        confidence = min(confidence, vendor.confidence)
        windows += 1
    return {
        'stt_language': language,
        'stt_language_evidence': 'audio_lid',
        'stt_language_confidence': confidence,
        'stt_language_windows': windows,
    }


async def prove_manifest(store, artifacts, item, manifest):
    """Re-authorize before source IO and each classifier; keep references immutable."""
    if normalized_stt_language(manifest['context'].get('stt_language')) not in AUTO_LANGUAGES:
        return manifest
    await run_blocking(db_executor, artifacts.authorize, item)
    allowed = {private_cloud_sync_bucket, derived_audio_bucket()}
    key = artifacts.key_for_owner(item.owner_id)
    wav = await run_blocking(
        storage_executor,
        materialize,
        MAGIC + json.dumps(manifest, separators=(',', ':')).encode(),
        item,
        lambda ref: read_reference(artifacts.client, ref, item.owner_id, item.conversation_id, allowed, key),
    )
    guard = ServingLanguageProbeGuard(store, item, authorize=batch_artifact_authorize)
    proof = await classify_wav(item, wav, guard)
    guard.raise_if_denied()
    await run_blocking(db_executor, artifacts.authorize, item)
    return {**manifest, 'context': {**manifest['context'], **proof}}
