"""TranslationCoordinator — orchestrates cost-effective real-time translation.

Replaces the scattered state in transcribe.py with a single coordinator that:
- Tracks per-segment committed text (prefix-safe)
- Gates translation on text stability signals
- Batches eligible segments into minimal GCP API calls
- Integrates with ConversationLanguageState for monolingual gating
- Supports negative caching to avoid re-checking known target-language text

Issue #6155.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Set, Tuple

from models.transcript_segment import TranscriptSegment, SENTENCE_ENDERS
from utils.translation import (
    TranslationNeed,
    classify_translation_need,
    get_cached_translation,
    set_negative_cache,
    TranslationService,
)
from utils.executors import db_executor, sync_executor, run_blocking
from utils.translation_cache import ConversationLanguageState, should_persist_translation, _normalize_base_language  # type: ignore[reportPrivateUsage]  # internal helper, intentional cross-module use

logger = logging.getLogger(__name__)


@dataclass
class SegmentState:
    """Per-segment tracking state for the coordinator."""

    segment_id: str
    committed_text: str = ''  # last stable text we translated (or decided to skip)
    latest_text: str = ''
    last_update_at: float = 0.0
    assembled_translation: Optional[str] = None
    detected_lang: Optional[str] = None
    version: int = 0  # monotonic for stale-write protection


# Stability signal flags
STABILITY_PUNCTUATION = 'punctuation'  # sentence-ending punctuation detected
STABILITY_SPEAKER_SWITCH = 'speaker_switch'  # different speaker started
STABILITY_SILENCE_GAP = 'silence_gap'  # >700ms silence gap
STABILITY_IS_FINAL = 'is_final'  # STT provider marked as final
STABILITY_SOFT_BOUNDARY = 'soft_boundary'  # >=12 tokens or >=3s open

# Soft boundary thresholds
SOFT_BOUNDARY_TOKEN_COUNT = 12
SOFT_BOUNDARY_OPEN_SECONDS = 3.0

# Batch aggregation window
BATCH_WINDOW_SECONDS = 0.25  # 250ms aggregation window


def _is_text_stable(text: str, signals: Set[str]) -> bool:
    """Check if text is considered stable enough for translation."""
    if not text:
        return False
    # Explicit stability signals
    if signals & {STABILITY_PUNCTUATION, STABILITY_SPEAKER_SWITCH, STABILITY_SILENCE_GAP, STABILITY_IS_FINAL}:
        return True
    if STABILITY_SOFT_BOUNDARY in signals:
        return True
    # Auto-detect sentence-ending punctuation
    stripped = text.rstrip()
    if stripped and stripped[-1] in SENTENCE_ENDERS:
        return True
    return False


def _compute_stability_signals(
    text: str, last_update_at: float, now: float, prev_speaker_id: Optional[int], curr_speaker_id: Optional[int]
) -> Set[str]:
    """Compute stability signals from text content and timing."""
    signals: Set[str] = set()
    stripped = text.rstrip()
    if stripped and stripped[-1] in SENTENCE_ENDERS:
        signals.add(STABILITY_PUNCTUATION)
    if prev_speaker_id is not None and curr_speaker_id is not None and prev_speaker_id != curr_speaker_id:
        signals.add(STABILITY_SPEAKER_SWITCH)
    # Soft boundary: text open for >=3s
    if last_update_at > 0 and (now - last_update_at) >= SOFT_BOUNDARY_OPEN_SECONDS:
        signals.add(STABILITY_SOFT_BOUNDARY)
    # Soft boundary: >=12 tokens
    token_count = len(text.split())
    if token_count >= SOFT_BOUNDARY_TOKEN_COUNT:
        signals.add(STABILITY_SOFT_BOUNDARY)
    return signals


class TranslationCoordinator:
    """Orchestrates real-time translation for a single WebSocket session.

    ## Architecture

    This coordinator implements SINGLE-PHASE translation: every stable text
    update is sent in full to the batch translator, which calls Google
    Translate V3 with the complete segment text. See DD-008 design doc
    (`deep-dives/DD-008-design-review.md`) for the planned TWO-PHASE
    architecture (streaming deltas + final full-sentence translation).

    ## Data Flow

    observe() → [stability gates] → batch_buffer → _flush_batch()
        → translate_units_batch() → [LRU → Redis → API]
        → on_translation_ready() → Firestore persist + WebSocket push

    ## Cost Note

    Because we send full text (not delta), each evolving segment generates
    multiple translations of overlapping content. Current cost: ~$4,282/mo
    for 284M characters. Target (with DD-008 fixes): ~$1,900–2,500/mo.

    ## Key Trade-off

    Translation quality (full context) vs cost (redundant chars).
    Currently optimized for quality. See DD-008 for path to both.
    """

    def __init__(
        self,
        target_language: str,
        translation_service: TranslationService,
        on_translation_ready: Callable[[str, str, str, str], Awaitable[None]],
        language_state: Optional[ConversationLanguageState] = None,
        source_language: str = "",
    ):
        self.target_language = target_language
        self.target_base = _normalize_base_language(target_language) or ''
        self.translation_service = translation_service
        self.on_translation_ready = on_translation_ready
        self.language_state = language_state or ConversationLanguageState(target_language)
        self.source_language = source_language

        self._segment_states: Dict[str, SegmentState] = {}
        self._version_counter = 0
        self._batch_buffer: List[Tuple[str, str, str, int]] = []  # (segment_id, text, conversation_id, version)
        self._batch_task: Optional[asyncio.Task[None]] = None
        self._flushing = False
        self._active = True
        self._last_speaker_id: Optional[int] = None  # tracks last speaker for switch detection

        # Metrics
        self.metrics = {
            'mono_gate_skips': 0,
            'classify_skips': 0,
            'classify_defers': 0,
            'classify_translates': 0,
            'batch_api_calls': 0,
            'negative_cache_sets': 0,
            'prefix_resets': 0,
        }

    def _next_version(self) -> int:
        self._version_counter += 1
        return self._version_counter

    def _get_or_create_state(self, segment_id: str) -> SegmentState:
        if segment_id not in self._segment_states:
            self._segment_states[segment_id] = SegmentState(segment_id=segment_id)
        return self._segment_states[segment_id]

    async def observe(
        self,
        updated_segments: List[TranscriptSegment],
        removed_ids: List[str],
        conversation_id: str,
    ):
        """Process updated segments and queue eligible ones for translation.

        Args:
            updated_segments: Segments that were added or modified.
            removed_ids: Segment IDs that were removed (merged away).
            conversation_id: Current conversation ID.
        """
        if not self._active and not self._flushing:
            return

        # Clean up removed segments
        for seg_id in removed_ids:
            self._segment_states.pop(seg_id, None)

        now = time.monotonic()

        for segment in updated_segments:
            if not segment or not segment.id:
                continue

            text = segment.text.strip() if segment.text else ''
            if not text:
                continue

            state = self._get_or_create_state(segment.id)

            # Prefix-safe check: if prefix changed, reset
            if state.committed_text and not text.startswith(state.committed_text):
                # Bump version and invalidate batch buffer BEFORE Redis lookup so
                # any in-flight batch job is rejected immediately as stale.
                state.version = self._next_version()
                self._batch_buffer = [entry for entry in self._batch_buffer if entry[0] != segment.id]
                if self._batch_task and not self._batch_task.done():
                    self._batch_task.cancel()
                    self._batch_task = None

                # Check if the new merged text was already translated (Redis cache)
                text_hash = hashlib.md5(text.encode()).hexdigest()
                redis_cached = await run_blocking(db_executor, get_cached_translation, text_hash, self.target_language)
                if redis_cached:
                    # Found in Redis — adopt as committed, skip re-translation
                    translated_text = redis_cached['text']
                    detected_lang = redis_cached.get('detected_lang', '')
                    # Apply cached detected language to conversation state so the
                    # monolingual gate doesn't incorrectly stay enabled for foreign text.
                    # Use the same logic as observe() but with known detected_lang.
                    if detected_lang:
                        _det_base = _normalize_base_language(detected_lang) or ''
                        if _det_base and _det_base != self.language_state.target_base:
                            # Foreign-language cache hit — exit monolingual gate
                            self.language_state.monolingual = False
                            self.language_state.consecutive_target = 0

                    # Guard: skip no-op "translations" that would spam UI badges.
                    if not should_persist_translation(text, translated_text, detected_lang, self.target_language):
                        state.committed_text = text
                        state.assembled_translation = translated_text
                        state.detected_lang = detected_lang
                        state.version = self._next_version()
                        state.latest_text = text
                        state.last_update_at = now
                        self._batch_buffer = [entry for entry in self._batch_buffer if entry[0] != segment.id]
                        # Cancel any in-flight batch task to prevent stale overwrite
                        if self._batch_task and not self._batch_task.done():
                            self._batch_task.cancel()
                            self._batch_task = None
                        self.metrics['prefix_resets'] += 1
                        continue  # Don't add to batch buffer
                    state.committed_text = text
                    state.assembled_translation = translated_text
                    state.detected_lang = detected_lang
                    state.latest_text = text
                    state.last_update_at = now
                    await self.on_translation_ready(segment.id, translated_text, detected_lang, conversation_id)
                    continue  # Don't add to batch buffer
                else:
                    state.committed_text = ''
                    state.assembled_translation = None
                    state.detected_lang = None
                    self.metrics['prefix_resets'] += 1

            # Only translate the new (uncommitted) portion
            new_text = text[len(state.committed_text) :].strip() if state.committed_text else text
            if not new_text:
                state.latest_text = text
                state.last_update_at = now
                continue

            # Save old last_update_at BEFORE overwriting (needed for time-based stability)
            old_last_update_at = state.last_update_at

            state.latest_text = text
            state.last_update_at = now

            # Monolingual gate check
            skip_mono = self.language_state.observe(new_text, speaker_id=segment.speaker_id)
            if skip_mono and not self.language_state.should_probe():
                self.metrics['mono_gate_skips'] += 1
                # Record as committed (target language, no translation needed)
                state.committed_text = text
                # Set negative cache for this text
                text_hash = hashlib.md5(text.encode()).hexdigest()
                set_negative_cache(text_hash, self.target_language)
                self.metrics['negative_cache_sets'] += 1
                continue

            # Compute stability signals using old timing and per-segment speaker tracking
            # prev_speaker comes from the last speaker we processed in this session
            signals = _compute_stability_signals(
                new_text, old_last_update_at, now, self._last_speaker_id, segment.speaker_id
            )
            self._last_speaker_id = segment.speaker_id

            is_stable = _is_text_stable(new_text, signals)

            # Classify translation need
            need = classify_translation_need(new_text, self.target_language, is_stable=is_stable)

            if need == TranslationNeed.SKIP:
                self.metrics['classify_skips'] += 1
                state.committed_text = text
                text_hash = hashlib.md5(text.encode()).hexdigest()
                set_negative_cache(text_hash, self.target_language)
                self.metrics['negative_cache_sets'] += 1
                continue

            if need == TranslationNeed.DEFER:
                self.metrics['classify_defers'] += 1
                continue

            # TRANSLATE — queue for batch
            self.metrics['classify_translates'] += 1
            version = self._next_version()
            state.version = version

            # DESIGN DECISION: We send `text` (full segment text) instead of
            # `new_text` (the uncommitted delta) to the batch translator.
            #
            # Rationale:
            # - Google Translate V3 translates each content string independently;
            #   full sentence context improves disambiguation (gender agreement,
            #   idioms like "estoy de acuerdo" → "I agree", not "acuerdo" → "agreement")
            # - The assembled_translation IS the final persisted result — it must be
            #   high quality since it's stored in Firestore and displayed to users
            #
            # Trade-off: This means evolving text ("Hola" → "Hola como" → "Hola como estas")
            # generates unique MD5 cache keys at every step, causing 3–4x redundant
            # translations per stabilized segment. See DD-008 for cost analysis and
            # proposed two-phase architecture that preserves quality while reducing cost.
            #
            # If you change this to send new_text (delta), you MUST also:
            # 1. Update assembly stitching logic in _flush_batch()
            # 2. Ensure stability gates filter out sub-sentence fragments
            # 3. Update the cache key strategy
            # 4. Measure translation quality regression in production
            self._batch_buffer.append((segment.id, text, conversation_id, version))

        # (Re)start batch aggregation timer
        if self._batch_buffer:
            if self._batch_task and not self._batch_task.done():
                self._batch_task.cancel()

            async def _batch_timer():
                await asyncio.sleep(BATCH_WINDOW_SECONDS)
                # Shield flush from cancellation to prevent losing in-flight results
                await asyncio.shield(self._flush_batch())

            self._batch_task = asyncio.ensure_future(_batch_timer())

    async def _flush_batch(self):
        """Translate all queued segments in a single batched API call.

        This method is shielded from cancellation to prevent losing in-flight results.
        """
        batch = list(self._batch_buffer)
        self._batch_buffer.clear()
        self._batch_task = None

        if not batch:
            return

        # Deduplicate and prepare translation units
        # Only translate segments whose version still matches (stale-write protection)
        valid_units: List[Tuple[str, str, str, int]] = []
        for seg_id, text, conv_id, version in batch:
            state = self._segment_states.get(seg_id)
            if not state or state.version != version:
                continue
            valid_units.append((seg_id, text, conv_id, version))

        if not valid_units:
            return

        # Prepare (unit_id, text) pairs for batch API
        api_units: List[Tuple[str, str]] = [(seg_id, text) for seg_id, text, _, _ in valid_units]

        self.metrics['batch_api_calls'] += 1
        logger.info(f"translate_coordinator [batch] units={len(api_units)}")

        try:
            # Run the sync GCP API call in a thread pool to avoid blocking the event loop
            results = await run_blocking(
                sync_executor,
                self.translation_service.translate_units_batch,
                self.target_language,
                api_units,
                source_language=self.source_language,
            )

            for seg_id, translated_text, detected_lang in results:
                # Find the corresponding entry
                matching: List[Tuple[str, str, str, int]] = [(s, t, c, v) for s, t, c, v in valid_units if s == seg_id]
                if not matching:
                    continue
                _, original_text, conv_id, version = matching[0]

                state = self._segment_states.get(seg_id)
                if not state or state.version != version:
                    continue

                # Check if translation is meaningful
                target_base = self.target_base
                if not should_persist_translation(original_text, translated_text, detected_lang, target_base):
                    # Distinguish real no-op (target-language text) from translation failure.
                    # A failure returns original_text with empty detected_lang — do NOT
                    # set negative cache or advance committed_text, so the segment can
                    # be retried on the next cycle.
                    if detected_lang:
                        # Genuine no-op: source is already in target language
                        text_hash = hashlib.md5(original_text.encode()).hexdigest()
                        set_negative_cache(text_hash, self.target_language)
                        self.metrics['negative_cache_sets'] += 1
                        state.committed_text = original_text
                    # else: translation failure — skip silently, allow retry
                    continue

                # Update state
                state.committed_text = original_text
                state.assembled_translation = translated_text
                state.detected_lang = detected_lang

                # Update language state from API response
                if detected_lang:
                    self.language_state.observe(original_text, speaker_id=None)

                # Notify via callback
                await self.on_translation_ready(seg_id, translated_text, detected_lang, conv_id)

        except Exception as e:
            logger.error(f"TranslationCoordinator batch error: {e}")

    async def flush(self):
        """Flush all pending translations before session cleanup."""
        self._flushing = True

        # Cancel batch timer and flush immediately
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
            self._batch_task = None
        await self._flush_batch()

        self._segment_states.clear()
        self._flushing = False
        self._active = False

    def handle_segment_merge(self, merge_map: Dict[str, str]):
        """Update tracking when segments are merged.

        merge_map: {removed_id -> surviving_id} — text from removed segments
        was merged into the surviving segment.
        """
        for removed_id, surviving_id in merge_map.items():
            removed_state = self._segment_states.pop(removed_id, None)
            if removed_state and surviving_id in self._segment_states:
                # The surviving segment's text changed — reset its committed state
                # so the full text gets re-evaluated
                self._segment_states[surviving_id].committed_text = ''
                self._segment_states[surviving_id].assembled_translation = None
