"""Speaker assignment state and embedding matching for listen sessions."""

from __future__ import annotations

import asyncio
import io
import logging
from collections import deque
from typing import Any, Deque, Dict, Mapping, Optional, Tuple, cast

import av
import config.speaker_match_scores as match_scores
import utils.stt.speaker_match as match_policy
import numpy as np
from pydantic import ValidationError

from config.speaker_prior import pinned_speaker_prior_enabled
from models.transcript_segment import SpeakerIdentityStatus
from utils.audio import AudioRingBuffer
from utils.live_speaker_collapse import LiveSpeakerCollapseMonitor
from utils.live_speaker_suggestions import reconcile_pinned_suggestion
from utils.log_sanitizer import sanitize
from utils.executors import storage_executor, sync_executor, run_blocking
from utils.other.storage import get_profile_audio_if_exists
from utils.speaker_permissions import named_speaker_prompts_allowed
from utils.speaker_sample import download_sample_audio
from utils.speaker_sample_migration import maybe_migrate_person_samples
from utils.manual_speaker_assignments import manual_owner_reserved, manual_rejected_speakers
from utils.stt.conversation_speakers import VOICE_MATCH_THRESHOLD
from utils.stt.speaker_embedding import compare_embeddings, extract_embedding_from_bytes
from utils.stt.speaker_match import (
    SPEAKER_MATCH_MAX_CLIPS,
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    SpeakerMatchDecision,
    arbitrate_owner_matches,
    mean_embedding,
    select_speaker_match,
)
from utils.transcribe_decisions import USER_SELF_PERSON_ID, should_spawn_speaker_match
from utils.transcribe_store import conversations_db, get_user_name, user_db
from utils.metrics import OMI_SPEAKER_ID_MATCH_EXITS_TOTAL, OMI_LIVE_SPEAKER_COLLAPSE_TOTAL
from utils.observability.owner_recognition import (
    live_decision_labels,
    pending_decision_target,
    record_live_speaker_decision,
    record_live_speaker_rollover,
)

logger = logging.getLogger(__name__)

MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS = 10.0

# The enumerated early-exit reasons for live speaker-ID matching. Every return
# before a match decision bumps exactly one of these (Prometheus counter label
# and one log line), so a user report of lost recognition is attributable
# instead of silently empty. The set is deliberately small:
# - window_outside_buffer: the segment's audio window does not intersect the
#   ring buffer's retained range (the post-failover clock bug's signature).
# - segment_shorter_than_minimum: the segment's own duration is below the
#   minimum embedding duration, before any window math.
# - no_fresh_audio: subtracting audio already embedded leaves nothing to embed.
# - window_shorter_than_minimum: the clamped extract window is below the minimum.
# - no_pcm: no buffered audio at all, or the extraction returned no PCM.
# - stale_generation: the matcher's conversation/profile state moved on while
#   this detection was queued, or the segment belongs to an earlier conversation.
# - already_mapped: a decision exists for this diarized speaker (a race drop,
#   not a loss).
# - rejected: the manual receipt named this voice as nobody, so it emits nothing.
SPEAKER_ID_EXIT_REASONS = frozenset(
    {
        'window_outside_buffer',
        'segment_shorter_than_minimum',
        'no_fresh_audio',
        'window_shorter_than_minimum',
        'no_pcm',
        'stale_generation',
        'already_mapped',
        'rejected',
        'manual_decision',
    }
)


def _read_file(path: str) -> bytes:
    with open(path, 'rb') as audio_file:
        return audio_file.read()


class SpeakerMatcher:
    def __init__(self, host: Any):
        self.host = host
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.person_embeddings: Dict[str, Dict[str, Any]] = {}
        self.speaker_to_person: Dict[int, tuple[str, str]] = {}
        self.segment_assignments: Dict[str, str] = {}
        self.segment_identity_status: Dict[str, SpeakerIdentityStatus] = {}
        self.voice_identity_status: Dict[int, SpeakerIdentityStatus] = {}
        self._voice_distances: Dict[int, Dict[str, float]] = {}
        self._voice_decisions: Dict[int, SpeakerMatchDecision] = {}
        self._voice_segments: Dict[int, str] = {}
        self._voice_centroids: Dict[int, Any] = {}
        self._voice_scopes: Dict[int, str] = {}
        # Pinned-speaker prior (flagged): people an unmatched voice resembles, and the
        # pinned near-miss already offered as a suggestion, per diarized speaker.
        self.voice_candidates: Dict[int, list] = {}
        self.match_scores: list = []
        self._suggested_person: Dict[int, str] = {}
        # manual or automatic, so a rollover can say which mappings were dropped.
        self._mapping_origin: Dict[int, str] = {}
        # Set by the rollover path before refresh; None means the caller did not report a receipt.
        self._pending_rollover_carry: Optional[set[int]] = None
        # Recent (embedding, clip seconds) per diarized speaker. A decision is made on
        # the centroid once enough audio has accumulated, instead of letting the first
        # clip that happens to land under the threshold stick for the whole session.
        self.speaker_evidence: Dict[int, Deque[Tuple[Any, float]]] = {}
        # Serialize evidence and decisions for each diarized speaker. Covered
        # intervals survive centroid eviction, but are pruned with the audio ring.
        self._speaker_locks: Dict[int, asyncio.Lock] = {}
        self._covered_audio: Dict[int, list[tuple[float, float]]] = {}
        self._generation = 0
        self.collapse_monitor = LiveSpeakerCollapseMonitor()
        self.tasks: set[asyncio.Task[Any]] = set()
        self._profile_conversation_id: Optional[str] = None
        self._profile_lock = asyncio.Lock()
        self._entitlement_lock = asyncio.Lock()
        self._named_speakers_allowed: Optional[bool] = None
        # The account owner's own first name, so hearing it in the transcript cannot
        # mint a person who is really the user. Resolved lazily by
        # resolve_owner_name(); used for display and as a veto, never as voice-match evidence.
        self.owner_name: Optional[str] = None
        self._owner_name_resolved = False

    def note_rollover_carry(self, carried_speaker_ids: set[int]) -> None:
        """Speaker ids the same-stream receipt will copy onto the next conversation.

        An empty set means the receipt carried nobody. Refresh counts a rollover
        only after this is called; a resume that merely changes conversation id
        does not.
        """
        self._pending_rollover_carry = set(carried_speaker_ids)

    async def refresh_for_conversation(self, conversation_id: str) -> None:
        async with self._profile_lock:
            if self._profile_conversation_id == conversation_id:
                self._pending_rollover_carry = None
                return
            carried = self._pending_rollover_carry
            self._pending_rollover_carry = None
            if self._profile_conversation_id is not None and carried is not None:
                record_live_speaker_rollover(self.speaker_to_person, self._mapping_origin, carried)
            self.clear()
            self._profile_conversation_id = conversation_id
            if self.host.state.speaker_id_enabled:
                await self._load_profiles()

    async def resolve_owner_name(self) -> Optional[str]:
        """The account owner's first name, resolved at most once per session.

        Resolved when an owner embedding or a textual introduction needs it.
        A failure leaves the veto off rather than failing the session.
        """
        if self._owner_name_resolved:
            return self.owner_name
        self._owner_name_resolved = True
        try:
            name = await self.host.persistence.call(get_user_name, self.host.request.uid, False)
        except Exception as error:
            logger.error('Speaker ID owner name load failed type=%s', type(error).__name__)
            return None
        if name and isinstance(name, str) and name.strip():
            self.owner_name = name.strip()
        return self.owner_name

    async def named_speakers_allowed(self) -> bool:
        """One subscription read per conversation; rotation/reconnect observes plan changes."""
        async with self._entitlement_lock:
            if self._named_speakers_allowed is None:
                generation = self._generation
                try:
                    allowed = await self.host.persistence.call(named_speaker_prompts_allowed, self.host.request.uid)
                except Exception as error:
                    # Unresolved is not denied: stay closed for this call and ask again next time.
                    logger.error('Speaker ID entitlement read failed type=%s', type(error).__name__)
                    return False
                if generation != self._generation:
                    return False
                self._named_speakers_allowed = bool(allowed)
            return bool(self._named_speakers_allowed)

    async def _load_profiles(self) -> None:
        if self.host.has_speech_profile:
            try:
                embedding = await self.host.persistence.call(user_db.get_user_speaker_embedding, self.host.request.uid)
                if embedding:
                    self.person_embeddings[USER_SELF_PERSON_ID] = {
                        'embedding': np.array(embedding, dtype=np.float32).reshape(1, -1),
                        'name': await self.resolve_owner_name() or 'The User',
                    }
                else:
                    path = await run_blocking(storage_executor, get_profile_audio_if_exists, self.host.request.uid)
                    if path:
                        profile = await run_blocking(storage_executor, _read_file, path)
                        result = await run_blocking(
                            sync_executor, cast(Any, extract_embedding_from_bytes), profile, 'speech_profile.wav'
                        )
                        del profile
                        self.person_embeddings[USER_SELF_PERSON_ID] = {
                            'embedding': result,
                            'name': await self.resolve_owner_name() or 'The User',
                        }
                        await self.host.persistence.call(
                            user_db.set_user_speaker_embedding, self.host.request.uid, result.flatten().tolist()
                        )
                    else:
                        logger.info('Speaker ID owner profile skipped reason=no_embedding_or_audio')
            except Exception as error:
                logger.error('Speaker ID user embedding load failed type=%s', type(error).__name__)
        try:
            if not await self.named_speakers_allowed():
                return
            people = await self.host.persistence.call(user_db.get_people, self.host.request.uid)
            for person in people:
                if person.get('speech_samples'):
                    person = await maybe_migrate_person_samples(self.host.request.uid, person)
                stored = person.get('speaker_embedding')
                verified_samples = bool(person.get('speech_samples')) and (person.get('speech_samples_version', 1) >= 3)
                vector: Optional[Any] = None
                if verified_samples:
                    if stored:
                        vector = np.array(stored, dtype=np.float32).reshape(1, -1)
                    else:
                        vector = await self._recover_person_embedding(person)
                if vector is not None:
                    self.person_embeddings[person['id']] = {
                        'embedding': vector,
                        'name': person['name'],
                        'pinned': person.get('pinned') is True,
                    }
        except Exception as error:
            logger.error('Speaker ID embeddings load failed type=%s', type(error).__name__)
            return

    async def load_and_run(self) -> None:
        state = self.host.state
        if not state.speaker_id_enabled:
            state.speaker_id_done.set()
            return
        # prepare() may already have loaded the first conversation's profiles.
        # Keep the loop alive even with zero enrolled people so a later
        # refresh_for_conversation can load a newly taught profile and still
        # consume the queue in this socket session.
        if self._profile_conversation_id is None:
            await self._load_profiles()
        while True:
            try:
                segment = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                if not state.active:
                    break
                continue
            speaker_id = segment['speaker_id']
            if should_spawn_speaker_match(
                speaker_already_mapped=speaker_id in self.speaker_to_person,
                duration=segment['duration'],
                min_audio_seconds=self.host.limits.speaker_id_min_audio,
            ):
                task = self.host.spawn(self.match(speaker_id, segment), name='speaker_match')
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
            else:
                # Dropped before a match is attempted; count it with the same
                # bounded vocabulary the match path uses.
                self._record_exit(
                    'already_mapped' if speaker_id in self.speaker_to_person else 'segment_shorter_than_minimum',
                    speaker_id,
                )
        state.speaker_id_done.set()

    def observe_segment(self, speaker_id: int, scope: str, segment_id: str) -> None:
        if self.collapse_monitor.observe(speaker_id, scope, segment_id):
            self._record_collapse()

    def _record_collapse(self) -> None:
        OMI_LIVE_SPEAKER_COLLAPSE_TOTAL.inc()
        logger.warning(
            'event=live_speaker_collapse consecutive_segments=%d rejected_matches=%d',
            self.collapse_monitor.consecutive_segments,
            self.collapse_monitor.rejected_matches,
        )

    def _session_log_id(self) -> Any:
        """Recording session id for speaker-ID log attribution; never the uid."""
        return getattr(self.host, 'recording_session_id', None)

    def _record_exit(self, reason: str, speaker_id: int) -> None:
        assert reason in SPEAKER_ID_EXIT_REASONS, reason
        OMI_SPEAKER_ID_MATCH_EXITS_TOTAL.labels(reason=reason).inc()
        logger.info('speaker_id_exit reason=%s speaker=%s session=%s', reason, speaker_id, self._session_log_id())

    async def _recover_person_embedding(self, person: Dict[str, Any]) -> Optional[Any]:
        """Rebuild a taught person's missing embedding from their stored samples.

        The teach path extracts the embedding inside a try/except that only logs, so a
        failed extraction leaves a person holding samples with no embedding, and nothing
        ever recomputes it. That person is then skipped here on every later session and
        can never be matched no matter how many times the user teaches them (#10434) —
        while the user's own profile self-heals through exactly this fallback above.

        Only reached for `speech_samples_version >= 3` samples, which already passed
        verify_and_transcribe_sample when they were stored, so this restores a lost
        embedding without reopening the quality gate that deliberately drops bad samples.
        """
        person_id = person.get('id')
        samples = person.get('speech_samples') or []
        if not samples:
            return None
        try:
            audio = await run_blocking(storage_executor, download_sample_audio, samples[0])
            if not audio:
                return None
            vector = await run_blocking(sync_executor, cast(Any, extract_embedding_from_bytes), audio, 'sample.wav')
            saved = await self.host.persistence.call(
                user_db.set_person_speaker_embedding,
                self.host.request.uid,
                person_id,
                vector.flatten().tolist(),
                expected_updated_at=person.get('updated_at'),
            )
            if not saved:
                return None
            logger.info('Speaker ID recovered missing person embedding person=%s', person_id)
            return vector
        except Exception as error:
            logger.error(
                'Speaker ID person embedding recovery failed person=%s type=%s', person_id, type(error).__name__
            )
            return None

    def _drop_reason(self, generation: int, conversation_id: Optional[str], speaker_id: int) -> Optional[str]:
        """Why this in-flight detection can no longer produce a decision, if it can't."""
        if generation != self._generation or self._profile_conversation_id != conversation_id:
            return 'stale_generation'
        if speaker_id in self.speaker_to_person:
            return 'already_mapped'
        return None

    async def match(self, speaker_id: int, segment: dict[str, Any]) -> None:
        conversation_id = self._profile_conversation_id
        if segment.get('conversation_id') is not None and segment['conversation_id'] != conversation_id:
            self._record_exit('stale_generation', speaker_id)
            return
        generation = self._generation
        lock = self._speaker_locks.setdefault(speaker_id, asyncio.Lock())
        async with lock:
            drop_reason = self._drop_reason(generation, conversation_id, speaker_id)
            if drop_reason is not None:
                if drop_reason == 'already_mapped':
                    await self._drop_rejected_mapping(speaker_id, segment, generation, conversation_id)
                self._record_exit(drop_reason, speaker_id)
                return
            await self._match_unmapped(speaker_id, segment, generation, conversation_id)

    async def _drop_rejected_mapping(
        self, speaker_id: int, segment: dict[str, Any], generation: int, conversation_id: Optional[str]
    ) -> None:
        """A mapped voice the receipt rejects must stop emitting its stale label."""
        if not conversation_id:
            return
        try:
            receipt = await self.host.persistence.call(
                conversations_db.get_manual_speaker_receipt, self.host.request.uid, conversation_id
            )
        except Exception as error:
            logger.warning('Speaker ID receipt load failed type=%s', type(error).__name__)
            return
        if generation != self._generation or self._profile_conversation_id != conversation_id:
            return
        if speaker_id in manual_rejected_speakers(receipt):
            self._retract_rejected_voice(speaker_id, segment.get('id'))
            self.host.state.speaker_map_dirty = True

    def _retract_rejected_voice(self, voice: int, segment_id: Optional[str]) -> None:
        stale = voice in self.speaker_to_person or voice in self._suggested_person
        self.speaker_to_person.pop(voice, None)
        self._mapping_origin.pop(voice, None)
        self.voice_candidates.pop(voice, None)
        self._suggested_person.pop(voice, None)
        self.voice_identity_status[voice] = SpeakerIdentityStatus.no_match
        if segment_id is not None:
            self.segment_identity_status[segment_id] = SpeakerIdentityStatus.no_match
            if stale:
                self.host.emit_speaker_suggestion(voice, '', '', segment_id, retracted=True)

    def _manual_voice_decision(self, receipt: Mapping, speaker_id: int) -> Optional[Mapping]:
        """The newest positive receipt decision naming this voice, if scope-bound ones match."""
        covering = (receipt.get('speakers') or {}).get(str(speaker_id))
        candidates = [covering] if isinstance(covering, Mapping) else []
        candidates += [
            entry
            for entry in (receipt.get('segments') or {}).values()
            if isinstance(entry, Mapping) and not entry.get('segment_only') and entry.get('speaker_id') == speaker_id
        ]
        positive = [entry for entry in candidates if not entry.get('rejection')]
        if not positive:
            return None
        decision = max(positive, key=lambda entry: entry.get('generation', 0))
        scope = decision.get('speaker_id_scope')
        if decision.get('source') == 'carried' and scope is not None and scope != self._voice_scopes.get(speaker_id):
            return None
        return decision

    async def _match_unmapped(
        self, speaker_id: int, segment: dict[str, Any], generation: int, conversation_id: Optional[str]
    ) -> None:
        try:
            ring_buffer: Optional[AudioRingBuffer] = self.host.state.audio_ring_buffer
            if ring_buffer is None:
                self._record_exit('no_pcm', speaker_id)
                return
            if segment['duration'] < self.host.limits.speaker_id_min_audio:
                self._record_exit('segment_shorter_than_minimum', speaker_id)
                return
            time_range = ring_buffer.get_time_range()
            if time_range is None:
                self._record_exit('no_pcm', speaker_id)
                return
            buffer_start, buffer_end = time_range
            if segment['abs_end'] <= buffer_start or segment['abs_start'] >= buffer_end:
                # The window does not intersect the retained audio at all —
                # e.g. a provider stream whose timestamps restarted at zero
                # after a failover while the window was still computed from
                # the first provider's clock. Name it; never fall through to
                # an inverted-clamp "too short" that hides the real cause.
                self._record_exit('window_outside_buffer', speaker_id)
                return
            # Streaming providers resend/extend merged segments. Subtract every
            # successfully embedded interval before choosing a fresh clip, so an
            # update cannot turn three seconds of speech into six seconds of evidence.
            covered = [(a, b) for a, b in self._covered_audio.get(speaker_id, []) if b > buffer_start]
            self._covered_audio[speaker_id] = covered
            fresh = [(max(buffer_start, segment['abs_start']), min(buffer_end, segment['abs_end']))]
            for used_start, used_end in covered:
                remaining = []
                for start, end in fresh:
                    if used_end <= start or used_start >= end:
                        remaining.append((start, end))
                    else:
                        if start < used_start:
                            remaining.append((start, used_start))
                        if used_end < end:
                            remaining.append((used_end, end))
                fresh = remaining
            if not fresh:
                # Zero fresh seconds left after subtracting embedded audio.
                self._record_exit('no_fresh_audio', speaker_id)
                return
            extract_start, extract_end = max(fresh, key=lambda interval: interval[1] - interval[0])
            if extract_end - extract_start > MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS:
                center = (extract_start + extract_end) / 2
                half_window = MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS / 2
                extract_start, extract_end = center - half_window, center + half_window
            if extract_end - extract_start < self.host.limits.speaker_id_min_audio:
                self._record_exit('window_shorter_than_minimum', speaker_id)
                return
            pcm = ring_buffer.extract(extract_start, extract_end)
            if not pcm:
                self._record_exit('no_pcm', speaker_id)
                return
            samples = np.frombuffer(pcm, dtype=np.int16)
            buffer = io.BytesIO()
            container = av.open(buffer, mode='w', format='wav')
            stream: Any = container.add_stream('pcm_s16le', rate=self.host.request.sample_rate)
            stream.layout = 'mono'
            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono')
            frame.rate = self.host.request.sample_rate
            for packet in stream.encode(frame):
                container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
            container.close()
            query = await run_blocking(
                sync_executor, cast(Any, extract_embedding_from_bytes), buffer.getvalue(), 'query.wav'
            )
            if (drop_reason := self._drop_reason(generation, conversation_id, speaker_id)) is not None:
                self._record_exit(drop_reason, speaker_id)
                return
            # Reserve only successful embeddings: a failed request may be retried.
            covered.append((extract_start, extract_end))
            clip_seconds = extract_end - extract_start
            evidence = self.speaker_evidence.setdefault(speaker_id, deque(maxlen=SPEAKER_MATCH_MAX_CLIPS))
            evidence.append((query, clip_seconds))
            evidence_seconds = sum(seconds for _, seconds in evidence)
            if evidence_seconds < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS:
                # Accumulation, not a drop: this speaker's next clip reuses the
                # evidence and reaches a decision, so it logs (below) but is not
                # an exit reason.
                record_live_speaker_decision(
                    pending_decision_target(owner_enrolled=USER_SELF_PERSON_ID in self.person_embeddings),
                    'pending',
                )
                logger.info(
                    'speaker_id_evidence surface=live speaker=%s clips=%d evidence_seconds=%.1f decision=pending session=%s',
                    speaker_id,
                    len(evidence),
                    evidence_seconds,
                    self._session_log_id(),
                )
                return
            centroid = mean_embedding([embedding for embedding, _ in evidence]) if len(evidence) > 1 else query
            distances = {
                person_id: compare_embeddings(centroid, value['embedding'])
                for person_id, value in self.person_embeddings.items()
            }
            self._voice_distances[speaker_id] = distances
            self._voice_decisions[speaker_id] = select_speaker_match(distances)
            self._voice_segments[speaker_id] = segment['id']
            self._voice_centroids[speaker_id] = centroid
            self._voice_scopes[speaker_id] = segment.get('speaker_id_scope') or ''
            # Receipt reads may await. Re-arbitrate the latest shared evidence
            # after the read, then publish synchronously.
            owner_reserved = False
            rejected: Dict[int, dict] = {}
            receipt: Mapping[str, Any] = {}
            if conversation_id:
                try:
                    receipt = await self.host.persistence.call(
                        conversations_db.get_manual_speaker_receipt, self.host.request.uid, conversation_id
                    )
                    owner_reserved = manual_owner_reserved(receipt)
                    rejected = manual_rejected_speakers(receipt)
                except Exception as error:
                    logger.warning('Speaker ID receipt load failed type=%s', type(error).__name__)
                    owner_reserved = True
            if (drop_reason := self._drop_reason(generation, conversation_id, speaker_id)) is not None:
                self._record_exit(drop_reason, speaker_id)
                return
            if speaker_id in rejected:
                for voice in rejected:
                    self._retract_rejected_voice(voice, self._voice_segments.get(voice))
                self.host.state.speaker_map_dirty = True
                self._record_match_score(speaker_id, self._voice_decisions[speaker_id], 'manual_rejected')
                self._record_exit('rejected', speaker_id)
                return
            manual = self._manual_voice_decision(receipt, speaker_id)
            if manual is not None:
                person_id = USER_SELF_PERSON_ID if manual.get('is_user') else manual.get('person_id')
                known = self.person_embeddings.get(person_id) if person_id else None
                voice_wide = manual.get('source') == 'carried' or manual is (receipt.get('speakers') or {}).get(
                    str(speaker_id)
                )
                if person_id and voice_wide:
                    # A manual label is authoritative without a loaded profile: on a
                    # free plan non-owner profiles stay unloaded, so resolve the name
                    # from the receipt decision's voice rather than dropping the map.
                    if known is not None:
                        name = known['name']
                    else:
                        person = await self.host.persistence.call(user_db.get_person, self.host.request.uid, person_id)
                        if (drop_reason := self._drop_reason(generation, conversation_id, speaker_id)) is not None:
                            self._record_exit(drop_reason, speaker_id)
                            return
                        name = (person or {}).get('name') or person_id
                    status = (
                        SpeakerIdentityStatus.user
                        if person_id == USER_SELF_PERSON_ID
                        else SpeakerIdentityStatus.not_user
                    )
                    self.speaker_to_person[speaker_id] = (person_id, name)
                    self._mapping_origin[speaker_id] = 'manual'
                    self.voice_identity_status[speaker_id] = status
                    self.segment_identity_status[segment['id']] = status
                    self.host.state.speaker_map_dirty = True
                self._record_match_score(speaker_id, self._voice_decisions[speaker_id], 'manual_decision', manual)
                self._record_exit('manual_decision', speaker_id)
                return
            voice_groups = self._provider_epoch_voice_groups()
            decisions = arbitrate_owner_matches(
                {v: d for v, d in self._voice_distances.items() if v not in rejected},
                {v: d for v, d in self._voice_decisions.items() if v not in rejected},
                owner_reserved=owner_reserved,
                voice_groups=voice_groups,
            )
            decision = decisions.get(speaker_id)
            if decision is not None:
                decision_target, decision_kind = live_decision_labels(
                    decision, owner_enrolled=USER_SELF_PERSON_ID in self.person_embeddings
                )
                record_live_speaker_decision(decision_target, decision_kind)
            logger.info(
                'speaker_id_decision surface=live speaker=%s clips=%d evidence_seconds=%.1f '
                'best=%s best_distance=%.3f runner_up_distance=%.3f accepted=%s owner_contended=%s '
                'session=%s conversation=%s',
                speaker_id,
                len(evidence),
                evidence_seconds,
                decision.best_id if decision else None,
                decision.best_distance if decision else 0.0,
                decision.runner_up_distance if decision else 0.0,
                decision.accepted if decision else False,
                decision.owner_contended if decision else False,
                self._session_log_id(),
                conversation_id,
            )
            if (drop_reason := self._drop_reason(generation, conversation_id, speaker_id)) is not None:
                self._record_exit(drop_reason, speaker_id)
                return
            if decision is not None and self.collapse_monitor.match(
                speaker_id, segment.get('speaker_id_scope') or '', segment['id'], accepted=decision.accepted
            ):
                self._record_collapse()
            # No awaits between arbitration and publishing the maps: another
            # speaker may finish embedding concurrently, but cannot publish a
            # decision based on a stale set of owner claims.
            prior = pinned_speaker_prior_enabled()
            pinned = {pid for pid, value in self.person_embeddings.items() if value.get('pinned')}
            assigned = {result.person_id for result in decisions.values() if result.person_id is not None}
            for voice in rejected:
                self._retract_rejected_voice(voice, self._voice_segments.get(voice))
            for voice, result in decisions.items():
                segment_id = self._voice_segments[voice]
                if result.person_id is not None:
                    self._suggested_person.pop(voice, None)
                    self.voice_candidates.pop(voice, None)
                    best_id = result.person_id
                    best_name = self.person_embeddings[best_id]['name']
                    changed = self.speaker_to_person.get(voice) != (best_id, best_name)
                    self.speaker_to_person[voice] = (best_id, best_name)
                    self._mapping_origin[voice] = 'automatic'
                    status = (
                        SpeakerIdentityStatus.user if best_id == USER_SELF_PERSON_ID else SpeakerIdentityStatus.not_user
                    )
                    if changed:
                        self.host.emit_speaker_suggestion(voice, best_id, best_name, segment_id)
                else:
                    if result.owner_contended:
                        self.speaker_to_person.pop(voice, None)
                        self._mapping_origin.pop(voice, None)
                        if self.voice_identity_status.get(voice) != SpeakerIdentityStatus.ambiguous:
                            logger.info(
                                'speaker_id_owner_contention surface=live speaker=%s session=%s',
                                voice,
                                self._session_log_id(),
                            )
                    status = (
                        SpeakerIdentityStatus.ambiguous if result.owner_contended else SpeakerIdentityStatus.no_match
                    )
                    if prior:
                        self._offer_pinned_suggestion(voice, result, pinned, segment_id, assigned)
                self._record_match_score(voice, result)
                self.voice_identity_status[voice] = status
                self.segment_identity_status[segment_id] = status
            self.host.state.speaker_map_dirty = True
            self.host.state.speaker_map_version = getattr(self.host.state, 'speaker_map_version', 0) + 1
        except Exception as error:
            if isinstance(error, ValidationError):
                issues = error.errors(include_input=False, include_context=False, include_url=False)
                first = issues[0] if issues else {}
                loc = first.get('loc')
                if isinstance(loc, tuple):
                    loc = '.'.join(str(part) for part in loc)
                logger.error(
                    'Speaker ID match failed speaker=%s type=%s session=%s '
                    'validation_model=%s validation_loc=%s validation_type=%s',
                    speaker_id,
                    type(error).__name__,
                    self._session_log_id(),
                    sanitize(error.title),
                    sanitize(loc),
                    sanitize(first.get('type')),
                )
            else:
                logger.error(
                    'Speaker ID match failed speaker=%s type=%s session=%s',
                    speaker_id,
                    type(error).__name__,
                    self._session_log_id(),
                )

    def _record_match_score(
        self,
        voice: int,
        decision: SpeakerMatchDecision,
        outcome: Optional[str] = None,
        manual: Optional[Mapping] = None,
    ) -> None:
        try:
            if match_scores.enabled():
                row = match_scores.summarize(
                    voice,
                    self._voice_distances[voice],
                    decision,
                    sum(seconds for _, seconds in self.speaker_evidence[voice]),
                    'capture',
                    threshold=match_policy.SPEAKER_MATCH_THRESHOLD,
                    margin_threshold=match_policy.SPEAKER_MATCH_MARGIN,
                    scope=self._voice_scopes.get(voice, ''),
                    outcome=outcome,
                )
                if outcome == 'manual_rejected':
                    row['accepted_person_id'] = None
                    row['status'] = 'no_match'
                if manual is not None:
                    row['accepted_person_id'] = (
                        USER_SELF_PERSON_ID if manual.get('is_user') else manual.get('person_id')
                    )
                    row['status'] = 'user' if manual.get('is_user') else 'not_user'
                self.match_scores = match_scores.merge(self.match_scores, [row])
        except Exception:
            match_scores.record_failure(logger)

    def _offer_pinned_suggestion(
        self, voice: int, result: SpeakerMatchDecision, pinned: set, segment_id: str, assigned: set
    ) -> None:
        """Pinned prior: record what this unmatched voice resembles; ask about a pinned near-miss.

        Never labels: the event carries an empty person_id, which every client treats as a
        suggestion only, plus ``suggested_person_id`` for clients that can show who.
        """
        reconcile_pinned_suggestion(self, voice, result, pinned, segment_id, assigned)

    def _provider_epoch_voice_groups(self) -> Dict[int, int]:
        """Reconcile a voice only across stamped provider epochs with close audio."""
        groups: Dict[int, int] = {}
        members: Dict[int, list[int]] = {}
        for voice, centroid in self._voice_centroids.items():
            scope = self._voice_scopes.get(voice)
            group = voice
            if scope:
                for representative, peers in members.items():
                    if all(
                        self._voice_scopes.get(peer)
                        and self._voice_scopes[peer] != scope
                        and compare_embeddings(centroid, self._voice_centroids[peer]) < VOICE_MATCH_THRESHOLD
                        for peer in peers
                    ):
                        group = representative
                        break
            groups[voice] = group
            members.setdefault(group, []).append(voice)
        return groups

    async def drain(self, *, timeout: float, label: str) -> None:
        if self.tasks:
            await self.host.drain(list(self.tasks), timeout=timeout, label=label)

    def clear(self) -> None:
        self._generation += 1
        self.collapse_monitor = LiveSpeakerCollapseMonitor()
        self._profile_conversation_id = None
        self._named_speakers_allowed = None
        self._covered_audio.clear()
        self.person_embeddings.clear()
        self.speaker_to_person.clear()
        self._mapping_origin.clear()
        self._pending_rollover_carry = None
        self.speaker_evidence.clear()
        self.segment_assignments.clear()
        self.segment_identity_status.clear()
        self.voice_identity_status.clear()
        self._voice_distances.clear()
        self._voice_decisions.clear()
        self._voice_segments.clear()
        self._voice_centroids.clear()
        self._voice_scopes.clear()
        self.voice_candidates.clear()
        self.match_scores.clear()
        self._suggested_person.clear()
