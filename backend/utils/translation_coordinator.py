"""TranslationCoordinator — orchestrates cost-effective real-time translation.

Replaces the scattered state in transcribe.py with a single coordinator that:
- Tracks per-segment committed text (prefix-safe)
- Gates translation on text stability signals
- Batches eligible segments into minimal provider API calls
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
    TranslationStatus,
    classify_translation_need,
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
    update is sent in full to the configured translation provider with the
    complete segment text. See DD-008 design doc
    (`deep-dives/DD-008-design-review.md`) for the planned TWO-PHASE
    architecture (streaming deltas + final full-sentence translation).

    ## Data Flow

    observe() → [stability gates] → batch_buffer → _flush_batch()
        → translate_outcomes() → [LRU → Redis → provider chain]
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
    ) -> None:
        """Process updated segments and queue eligible ones for translation.

        Args:
            updated_segments: Segments that were added or modified.
            removed_ids: Segment IDs that were removed (merged away).
            conversation_id: Current conversation ID.
        """
        if not self._active and not self._flushing:
            return

        for seg_id in removed_ids:
            self._segment_states.pop(seg_id, None)

        now = time.monotonic()
        for segment in updated_segments:
            await self._observe_segment(segment, conversation_id, now)

        self._restart_batch_timer()

    async def _observe_segment(self, segment: TranscriptSegment, conversation_id: str, now: float) -> None:
        if not segment or not segment.id:
            return

        text = segment.text.strip() if segment.text else ''
        if not text:
            return

        state = self._get_or_create_state(segment.id)
        if await self._reconcile_changed_prefix(segment.id, text, state, conversation_id, now):
            return

        new_text = text[len(state.committed_text) :].strip() if state.committed_text else text
        if not new_text:
            state.latest_text = text
            state.last_update_at = now
            return

        old_last_update_at = state.last_update_at
        state.latest_text = text
        state.last_update_at = now

        skip_mono = self.language_state.observe(new_text, speaker_id=segment.speaker_id)
        if skip_mono and not self.language_state.should_probe():
            await self._commit_target_language_text(state, text, 'mono_gate_skips')
            return

        signals = _compute_stability_signals(
            new_text,
            old_last_update_at,
            now,
            self._last_speaker_id,
            segment.speaker_id,
        )
        self._last_speaker_id = segment.speaker_id
        need = classify_translation_need(
            new_text,
            self.target_language,
            is_stable=_is_text_stable(new_text, signals),
        )

        if need == TranslationNeed.SKIP:
            await self._commit_target_language_text(state, text, 'classify_skips')
        elif need == TranslationNeed.DEFER:
            self.metrics['classify_defers'] += 1
        else:
            self._queue_translation(segment.id, text, conversation_id, state)

    async def _reconcile_changed_prefix(
        self,
        segment_id: str,
        text: str,
        state: SegmentState,
        conversation_id: str,
        now: float,
    ) -> bool:
        """Reconcile a non-prefix update, returning whether cached work handled it."""
        if not state.committed_text or text.startswith(state.committed_text):
            return False

        # Invalidate before cache I/O so an in-flight result cannot win a stale write.
        self._invalidate_segment_work(segment_id, state)
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cached = await run_blocking(
            db_executor,
            self.translation_service.get_cached_translation,
            text_hash,
            self.target_language,
        )
        if cached is None:
            state.committed_text = ''
            state.assembled_translation = None
            state.detected_lang = None
            self.metrics['prefix_resets'] += 1
            return False

        translated_text = cached['text']
        detected_lang = cached.get('detected_lang', '')
        if detected_lang:
            self.language_state.observe_detection(detected_lang, 1.0)

        if not should_persist_translation(text, translated_text, detected_lang, self.target_language):
            # Cache I/O yielded; invalidate again in case newer work arrived meanwhile.
            self._invalidate_segment_work(segment_id, state)
            self._adopt_cached_prefix(state, text, translated_text, detected_lang, now)
            self.metrics['prefix_resets'] += 1
            return True

        self._adopt_cached_prefix(state, text, translated_text, detected_lang, now)
        await self.on_translation_ready(segment_id, translated_text, detected_lang, conversation_id)
        return True

    @staticmethod
    def _adopt_cached_prefix(
        state: SegmentState,
        text: str,
        translated_text: str,
        detected_lang: str,
        now: float,
    ) -> None:
        state.committed_text = text
        state.assembled_translation = translated_text
        state.detected_lang = detected_lang
        state.latest_text = text
        state.last_update_at = now

    async def _commit_target_language_text(
        self,
        state: SegmentState,
        text: str,
        skip_metric: str,
    ) -> None:
        """Commit a local skip and persist its shared negative-cache decision."""
        self.metrics[skip_metric] += 1
        state.committed_text = text
        text_hash = hashlib.md5(text.encode()).hexdigest()
        await run_blocking(
            db_executor,
            self.translation_service.set_negative_cache,
            text_hash,
            self.target_language,
        )
        self.metrics['negative_cache_sets'] += 1

    def _queue_translation(
        self,
        segment_id: str,
        text: str,
        conversation_id: str,
        state: SegmentState,
    ) -> None:
        """Queue full text for provider context; delta translation remains deferred by DD-008."""
        self.metrics['classify_translates'] += 1
        version = self._next_version()
        state.version = version
        self._batch_buffer.append((segment_id, text, conversation_id, version))

    def _invalidate_segment_work(self, segment_id: str, state: SegmentState) -> None:
        state.version = self._next_version()
        self._batch_buffer = [entry for entry in self._batch_buffer if entry[0] != segment_id]
        self._cancel_batch_timer()

    def _cancel_batch_timer(self) -> None:
        if self._batch_task and not self._batch_task.done():
            self._batch_task.cancel()
        self._batch_task = None

    def _restart_batch_timer(self) -> None:
        if not self._batch_buffer:
            return
        self._cancel_batch_timer()
        self._batch_task = asyncio.ensure_future(self._flush_after_batch_window())

    async def _flush_after_batch_window(self) -> None:
        await asyncio.sleep(BATCH_WINDOW_SECONDS)
        # Shield provider work from timer cancellation once flushing has begun.
        await asyncio.shield(self._flush_batch())

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
            # Run the sync provider call in a thread pool to avoid blocking the event loop
            outcomes = await run_blocking(
                sync_executor,
                self.translation_service.translate_outcomes,
                self.target_language,
                api_units,
                source_language=self.source_language,
            )
            if len(outcomes) != len(valid_units):
                raise RuntimeError('Translation service returned the wrong number of outcomes')

            for outcome, (seg_id, original_text, conv_id, version) in zip(outcomes, valid_units):
                state = self._segment_states.get(seg_id)
                if not state or state.version != version:
                    continue
                if outcome.status == TranslationStatus.failed:
                    continue

                # Check if translation is meaningful
                target_base = self.target_base
                if not should_persist_translation(
                    original_text,
                    outcome.text,
                    outcome.detected_language,
                    target_base,
                ):
                    detected_base = _normalize_base_language(outcome.detected_language) or ''
                    if outcome.status == TranslationStatus.unchanged:
                        if outcome.detected_language:
                            self.language_state.observe_detection(outcome.detected_language, 1.0)
                        if detected_base == target_base:
                            # Only target-language no-ops belong in the negative cache.
                            text_hash = hashlib.md5(original_text.encode()).hexdigest()
                            await run_blocking(
                                db_executor,
                                self.translation_service.set_negative_cache,
                                text_hash,
                                self.target_language,
                            )
                            self.metrics['negative_cache_sets'] += 1
                        state.committed_text = original_text
                    continue

                # Update state
                state.committed_text = original_text
                state.assembled_translation = outcome.text
                state.detected_lang = outcome.detected_language

                # Update language state from API response
                if outcome.detected_language:
                    self.language_state.observe_detection(outcome.detected_language, 1.0)

                # Notify via callback
                await self.on_translation_ready(
                    seg_id,
                    outcome.text,
                    outcome.detected_language,
                    conv_id,
                )

        except (RuntimeError, ValueError) as error:
            logger.error('TranslationCoordinator batch error: %s', error)

    async def flush(self):
        """Flush all pending translations before session cleanup."""
        self._flushing = True

        self._cancel_batch_timer()
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
