"""Speaker assignment state and embedding matching for listen sessions."""

from __future__ import annotations

import asyncio
import io
import logging
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Deque, Dict, Mapping, Optional, Tuple, cast

import av
import config.speaker_match_scores as match_scores
import utils.stt.speaker_match as match_policy
import numpy as np
from pydantic import ValidationError

from config.speaker_prior import pinned_speaker_prior_enabled
from models.transcript_segment import SpeakerIdentityStatus
from database.firestore_read_metrics import FirestoreReadSite
from utils.audio import AudioRingBuffer
from utils.live_speaker_collapse import LiveSpeakerCollapseMonitor
from utils.live_owner_continuity import OwnerContinuity, FRESH_SECONDS
from utils.live_speaker_suggestions import reconcile_pinned_suggestion
from utils.log_sanitizer import sanitize
from utils.executors import storage_executor, sync_executor, run_blocking
from utils.other.storage import get_profile_audio_if_exists
from utils.speaker_permissions import named_speaker_prompts_allowed
from utils.speaker_sample import download_sample_audio
from utils.speaker_sample_migration import maybe_migrate_person_samples
from utils.manual_speaker_assignments import manual_owner_reserved, manual_rejected_speakers
from utils.stt.conversation_speakers import VOICE_MATCH_THRESHOLD
from utils.stt.owner_profile import load_owner_embedding, validated_embedding
from utils.stt.speaker_embedding import compare_embeddings, extract_embedding_from_bytes
from utils.stt.speaker_match import (
    SPEAKER_MATCH_MAX_CLIPS,
    SPEAKER_MATCH_MIN_EVIDENCE_SECONDS,
    SpeakerMatchDecision,
    arbitrate_owner_matches,
    mean_embedding,
    owner_near_miss,
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
    record_owner_reconnect,
)

logger = logging.getLogger(__name__)

MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS = 10.0
MAX_SPEAKER_VOICES = 128
MAX_VOICE_EMBEDDING_ATTEMPTS = 12
# A small initial burst plus wall-time refill: at most 16 + 240 = 256
# attempts in the first socket-hour, then 240/hour in steady state. Client
# timestamps, profile refresh and conversation churn cannot mint tokens.
SOCKET_EMBEDDING_BURST = 16
SOCKET_EMBEDDING_REFILL_PER_SECOND = 240 / 3600
MAX_OWNER_FAILED_LOADS = 8
MAX_OWNER_PROFILE_RETRIES = 7
MAX_OWNER_AUDIO_REPAIRS = 3

# The enumerated early-exit reasons for live speaker-ID matching. Every return
# before a match decision bumps exactly one of these (Prometheus counter label
# and one log line), so a user report of lost recognition is attributable
# instead of silently empty. The set is deliberately small:
# - window_outside_buffer: the segment's audio window does not intersect the
#   ring buffer's retained range (the post-failover clock bug's signature).
# - segment_shorter_than_minimum: the segment's own duration is below the
#   minimum embedding duration, before any window math.
# - no_fresh_audio: subtracting audio already embedded leaves nothing to embed.
# - window_shorter_than_minimum: pooled fresh intervals or extracted PCM
#   remain below the current extraction floor; later fragments may complete them.
# - no_pcm: no buffered audio at all, or no pooled interval returned PCM.
# - stale_generation: the matcher's conversation/profile state moved on while
#   this detection was queued, or the segment belongs to an earlier conversation.
# - already_mapped: a decision exists for this diarized speaker (a race drop,
#   not a loss).
# - rejected: the manual receipt named this voice as nobody, so it emits nothing.
# - authority_unavailable: embedding was spent, but final authority vetoed publication.
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
        'voice_capacity',
        'embedding_budget',
        'authority_unavailable',
    }
)


@dataclass(frozen=True)
class FinalSpeakerAuthority:
    roster: tuple[bool, set[tuple[str, int]]]
    receipt: Mapping[str, Any]
    rollover_donor_receipt: Optional[dict] = None
    unavailable: bool = False

    @property
    def owner_reserved(self) -> bool:
        return manual_owner_reserved(self.receipt)


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
        self._competition_only: set[int] = set()
        self._competition_fresh: set[int] = set()
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
        self._lock_users: Dict[asyncio.Lock, int] = {}
        self._covered_audio: Dict[int, list[tuple[float, float]]] = {}
        self._pending_audio: Dict[int, list[tuple[float, float]]] = {}
        self._embedding_attempts: Dict[int, int] = {}
        self._socket_embedding_tokens = float(SOCKET_EMBEDDING_BURST)
        self._socket_embedding_refilled_at = time.monotonic()
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
        self._profile_retry_after = 0.0
        self._owner_load_failed = False
        self._owner_failed_loads = 0
        self._owner_profile_retries = 0
        self._owner_audio_repairs = 0
        self._owner_audio_retry_after = 0.0
        self.continuity = OwnerContinuity(self)

    def note_rollover_carry(self, carried_speaker_ids: set[int]) -> None:
        """Manual receipt ids copied by this rollover; automatic ids join after validation."""
        self._pending_rollover_carry = set(carried_speaker_ids)

    async def refresh_for_conversation(
        self,
        conversation_id: str,
        *,
        owner_carry_scope: Optional[str] = None,
        owner_carry_donor: Optional[Mapping] = None,
    ) -> None:
        async with self._profile_lock:
            if self._profile_conversation_id == conversation_id:
                self._pending_rollover_carry = None
                if (
                    self._owner_load_failed
                    and self._owner_failed_loads < MAX_OWNER_FAILED_LOADS
                    and self._owner_profile_retries < MAX_OWNER_PROFILE_RETRIES
                    and time.monotonic() >= self._profile_retry_after
                ):
                    await self._load_profiles(owner_only=True)
                return
            # Preserve the complete evidenced same-scope competition, not just
            # its owner winner. Dropping a runner-up would weaken joint arbitration.
            donor = owner_carry_donor or {}
            receipt = donor.get('manual_speaker_assignments') or {}
            old_owner = self.person_embeddings.get(USER_SELF_PERSON_ID)
            old_mappings = dict(self.speaker_to_person)
            old_origins = dict(self._mapping_origin)
            old_generation = self._generation
            reasons = {}
            candidates = set()
            retained = {}
            for voice, identity in old_mappings.items():
                if old_origins.get(voice) == 'manual':
                    reasons[voice] = 'manual_not_copied'
                elif identity[0] != USER_SELF_PERSON_ID:
                    reasons[voice] = 'non_owner'
                elif not owner_carry_scope:
                    reasons[voice] = 'no_scope'
                elif not donor:
                    reasons[voice] = 'donor_unavailable'
                elif any(donor.get(k) for k in ('deleted', 'discarded', 'is_locked')):
                    reasons[voice] = 'donor_ineligible'
                elif self._voice_scopes.get(voice) != owner_carry_scope:
                    reasons[voice] = 'scope_changed'
                elif (
                    manual_owner_reserved(receipt)
                    or voice in manual_rejected_speakers(receipt)
                    or self._manual_voice_decision(receipt, voice) is not None
                ):
                    reasons[voice] = 'manual_override'
                elif (
                    voice not in self._voice_centroids
                    or voice not in self.speaker_evidence
                    or self._voice_decisions.get(voice) is None
                    or self._voice_decisions[voice].person_id != USER_SELF_PERSON_ID
                ):
                    reasons[voice] = 'no_evidence'
                else:
                    candidates.add(voice)
                    reasons[voice] = 'not_restored'
            if old_generation != self._generation:
                return
            if candidates:
                for voice, centroid in self._voice_centroids.items():
                    if self._voice_scopes.get(voice) == owner_carry_scope and voice in self.speaker_evidence:
                        retained[voice] = (centroid, self.speaker_evidence[voice], self._covered_audio.get(voice, []))
            carried = self._pending_rollover_carry
            if carried is not None:
                carried = {voice for voice in carried if old_origins.get(voice) == 'manual'}
            count_rollover = self._profile_conversation_id is not None and carried is not None
            # Preserve candidate carry attempts across the awaits too: a match
            # may run while the profiles/donor are loading. Uncarried ids get
            # a fresh per-conversation allowance after validation completes.
            retained_attempts = {
                voice: attempts
                for voice, attempts in self._embedding_attempts.items()
                if voice in candidates or voice in (carried or set())
            }
            self.clear()
            self._embedding_attempts.update(retained_attempts)
            self._profile_conversation_id = conversation_id
            carry_generation = self._generation
            automatic_carry: set[int] = set()
            if self.host.state.speaker_id_enabled:
                await self._load_profiles()
                await self.continuity.start()
            current_receipt = {}
            current_receipt_unavailable = False
            read_failed = False
            if candidates:
                try:
                    donor = (
                        await self.host.persistence.call(
                            conversations_db.get_conversation,
                            self.host.request.uid,
                            donor['id'],
                            read_site=FirestoreReadSite.LISTEN_CLIENT_ID_PROBE,
                        )
                        or {}
                    )
                except Exception:
                    read_failed = True
            if candidates or self._voice_centroids:
                try:
                    current_receipt = await self.host.persistence.call(
                        conversations_db.get_manual_speaker_receipt, self.host.request.uid, conversation_id
                    )
                except Exception:
                    read_failed = True
                    current_receipt_unavailable = True
            receipt = donor.get('manual_speaker_assignments') or {}
            final_authority = await self._final_authority(
                current_receipt,
                receipt_unavailable=current_receipt_unavailable,
                rollover_donor=donor.get('id') if candidates else None,
                include_short=any(
                    sum(seconds for _, seconds in evidence) < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
                    for _, evidence, _ in retained.values()
                ),
            )
            authority, current_receipt = final_authority.roster, final_authority.receipt
            final_donor_receipt = final_authority.rollover_donor_receipt
            if carry_generation == self._generation and self._profile_conversation_id == conversation_id:
                if not self._allow_authority_publication(final_authority):
                    self._release_rollover_attempts(retained_attempts, carried or set())
                    reasons.update({voice: 'donor_unavailable' for voice in candidates})
                    if count_rollover:
                        record_live_speaker_rollover(old_mappings, old_origins, carried, reasons)
                    return
            if candidates:
                if final_donor_receipt is None:
                    read_failed = True
                else:
                    receipt = final_donor_receipt
            # Receiving, acoustic donor and immediate rollover donor authority
            # share one final transaction snapshot. Publication does not yield.
            epoch = getattr(getattr(self.host, 'receiver', None), 'speaker_provider_epoch', None)
            owner = self.person_embeddings.get(USER_SELF_PERSON_ID)
            gate = None
            if carry_generation != self._generation or self._profile_conversation_id != conversation_id:
                gate = 'stale_generation'
            elif read_failed or not donor:
                gate = 'donor_unavailable'
            elif any(donor.get(k) for k in ('deleted', 'discarded', 'is_locked')):
                gate = 'donor_ineligible'
            elif owner is None or old_owner is None:
                gate = 'profile_unavailable'
            elif not np.array_equal(owner['embedding'], old_owner['embedding']):
                gate = 'profile_changed'
            elif getattr(epoch, 'current_scope', None) != owner_carry_scope:
                gate = 'scope_changed'
            existing = set(self._voice_distances)
            restored = set()
            if gate:
                reasons.update({voice: gate for voice in candidates})
            elif candidates:
                assert owner_carry_scope is not None
                for voice, (centroid, evidence, covered) in retained.items():
                    if voice not in existing:
                        self._voice_scopes[voice] = owner_carry_scope
                    if (
                        manual_owner_reserved(receipt)
                        or manual_owner_reserved(current_receipt)
                        or voice in manual_rejected_speakers(receipt)
                        or voice in manual_rejected_speakers(current_receipt)
                        or self._manual_voice_decision(receipt, voice) is not None
                        or self._manual_voice_decision(current_receipt, voice) is not None
                    ):
                        reasons[voice] = 'manual_override'
                        continue
                    if voice in existing:
                        reasons[voice] = 'current_evidence'
                        continue
                    if self._admit_voice(voice) is None:
                        reasons[voice] = 'voice_capacity'
                        continue
                    self._voice_centroids[voice] = centroid
                    self.speaker_evidence[voice] = evidence
                    self._covered_audio[voice] = covered
                    self._voice_scopes[voice] = owner_carry_scope
                    self._voice_segments[voice] = ''
                    restored.add(voice)
                self._competition_only.update(restored - candidates)
            if (
                self._voice_centroids
                and carry_generation == self._generation
                and self._profile_conversation_id == conversation_id
            ):
                # Revalidate both carried evidence and matches that ran while
                # profiles/receipts were loading, against the completed roster.
                qualified = self._rebuild_voice_decisions(authority)
                rejected = manual_rejected_speakers(current_receipt)
                decisions = arbitrate_owner_matches(
                    {v: d for v, d in self._voice_distances.items() if v not in rejected},
                    {v: d for v, d in self._voice_decisions.items() if v not in rejected},
                    owner_reserved=final_authority.owner_reserved,
                    voice_groups=self._provider_epoch_voice_groups(),
                )
                # Runner-up evidence constrains the owner but never automatically
                # carries a non-owner identity across a conversation boundary.
                self._publish_decisions(
                    {
                        v: (replace(d, person_id=None) if v in restored and d.person_id != USER_SELF_PERSON_ID else d)
                        for v, d in decisions.items()
                        if v in existing or v in candidates
                    }
                )
                for voice in candidates & restored:
                    decision = decisions.get(voice)
                    if decision and decision.person_id == USER_SELF_PERSON_ID:
                        reasons[voice] = 'automatic'
                        automatic_carry.add(voice)
                        if carried is not None:
                            carried.add(voice)
                    else:
                        reasons[voice] = (
                            'donor_authority'
                            if sum(seconds for _, seconds in self.speaker_evidence[voice])
                            < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
                            and voice not in qualified
                            else 'owner_contended' if decision and decision.owner_contended else 'voiceprint_rejected'
                        )
            if carry_generation == self._generation:
                self._release_rollover_attempts(retained_attempts, (carried or set()) | automatic_carry)
            if count_rollover:
                record_live_speaker_rollover(old_mappings, old_origins, carried, reasons)
            await self.continuity.update(current_receipt, force=True, generation=carry_generation)

    def _release_rollover_attempts(self, retained: Mapping[int, int], carried: set[int]) -> None:
        for voice, attempts in retained.items():
            if voice not in carried:
                self._embedding_attempts[voice] -= attempts
                if not self._embedding_attempts[voice] and voice not in self._speaker_locks:
                    del self._embedding_attempts[voice]

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

    async def _load_profiles(self, *, owner_only: bool = False) -> None:
        eligible = (
            getattr(self.host.request, 'include_speech_profile', True)
            and not getattr(self.host.request, 'onboarding_mode', False)
            and not getattr(self.host, 'is_multi_channel', False)
            and not getattr(self.host, 'use_custom_stt', False)
        )
        self._owner_load_failed = False
        may_load = self._owner_failed_loads < MAX_OWNER_FAILED_LOADS and (
            not owner_only or self._owner_profile_retries < MAX_OWNER_PROFILE_RETRIES
        )
        if eligible and not may_load:
            self._owner_load_failed = True
        if eligible and may_load:
            if owner_only:
                self._owner_profile_retries += 1
            try:
                stored_embedding = await self.host.persistence.call(
                    user_db.get_user_speaker_embedding, self.host.request.uid
                )
                repair = (
                    validated_embedding(stored_embedding) is None
                    and not stored_embedding
                    and self.host.has_speech_profile
                    and self._owner_audio_repairs < MAX_OWNER_AUDIO_REPAIRS
                    and time.monotonic() >= self._owner_audio_retry_after
                )
                if repair:
                    self._owner_audio_repairs += 1
                    self._owner_audio_retry_after = time.monotonic() + 30.0 * 4 ** (self._owner_audio_repairs - 1)
                vector = await run_blocking(
                    sync_executor,
                    load_owner_embedding,
                    self.host.request.uid,
                    users=user_db,
                    stored_embedding=stored_embedding,
                    allow_audio_repair=repair,
                    audio_loader=get_profile_audio_if_exists,
                    read_file=_read_file,
                    extractor=extract_embedding_from_bytes,
                )
                if vector is not None:
                    self.host.has_speech_profile = True
                    self.person_embeddings[USER_SELF_PERSON_ID] = {
                        'embedding': vector,
                        'name': await self.resolve_owner_name() or 'The User',
                    }
                else:
                    self._owner_load_failed = True
                    self.person_embeddings.pop(USER_SELF_PERSON_ID, None)
                    if self.host.has_speech_profile:
                        logger.info('Speaker ID owner profile skipped reason=no_embedding_or_audio')
            except Exception as error:
                self._owner_load_failed = True
                logger.error('Speaker ID user embedding load failed type=%s', type(error).__name__)
            if self._owner_load_failed:
                self._owner_failed_loads += 1
        self._profile_retry_after = time.monotonic() + min(480.0, 30.0 * 2 ** max(0, self._owner_failed_loads - 1))
        if owner_only:
            if not self._owner_load_failed and USER_SELF_PERSON_ID in self.person_embeddings:
                await self._reevaluate_loaded_owner()
            # Paid people and entitlement were loaded by the conversation refresh.
            # Owner outages must not turn their projection into a polling loop.
            return
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
                        vector = validated_embedding(stored)
                    else:
                        vector = await self._recover_person_embedding(person)
                if vector is not None and (
                    USER_SELF_PERSON_ID not in self.person_embeddings
                    or vector.size == self.person_embeddings[USER_SELF_PERSON_ID]['embedding'].size
                ):
                    self.person_embeddings[person['id']] = {
                        'embedding': vector,
                        'name': person['name'],
                        'pinned': person.get('pinned') is True,
                    }
        except Exception as error:
            logger.error('Speaker ID embeddings load failed type=%s', type(error).__name__)
            return

    async def _reevaluate_loaded_owner(self) -> bool:
        """A taught/recovered owner can use retained evidence after model quota exhaustion."""
        generation, conversation_id = self._generation, self._profile_conversation_id
        if not self._voice_centroids:
            return False
        receipt: Mapping[str, Any] = {}
        if conversation_id:
            try:
                receipt = await self.host.persistence.call(
                    conversations_db.get_manual_speaker_receipt, self.host.request.uid, conversation_id
                )
            except Exception:
                return False
        if generation != self._generation or conversation_id != self._profile_conversation_id:
            return False
        final_authority = await self._final_authority(receipt)
        authority, receipt = final_authority.roster, final_authority.receipt
        if generation != self._generation or conversation_id != self._profile_conversation_id:
            return False
        if not self._allow_authority_publication(final_authority):
            return False
        rejected = manual_rejected_speakers(receipt)
        self._rebuild_voice_decisions(authority)
        automatic = {
            v: d
            for v, d in self._voice_decisions.items()
            if v not in rejected and self._manual_voice_decision(receipt, v) is None
        }
        decisions = arbitrate_owner_matches(
            {v: self._voice_distances[v] for v in automatic},
            automatic,
            owner_reserved=final_authority.owner_reserved,
            voice_groups=self._provider_epoch_voice_groups(),
        )
        self._publish_decisions(decisions)
        await self.continuity.update(receipt, force=True, generation=generation)
        return True

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
            await self.continuity.start()
        while True:
            try:
                segment = await asyncio.wait_for(self.queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                await self.continuity.refresh()
                if self._profile_conversation_id is not None and self._owner_load_failed:
                    await self.refresh_for_conversation(self._profile_conversation_id)
                if not state.active:
                    break
                continue
            if self._profile_conversation_id is not None and self._owner_load_failed:
                await self.refresh_for_conversation(self._profile_conversation_id)
            speaker_id = segment['speaker_id']
            if should_spawn_speaker_match(
                speaker_already_mapped=speaker_id in self.speaker_to_person,
                duration=segment['duration'],
                min_audio_seconds=0.0,
            ):
                if len(self.tasks) >= 16:
                    await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)
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
        if speaker_id in self._voice_decisions and self._voice_scopes.get(speaker_id) == scope:
            previous_segment = self._voice_segments.get(speaker_id)
            if segment_id != previous_segment:
                self.continuity.observe(speaker_id)
            if previous_segment and previous_segment not in self.segment_assignments:
                self.segment_identity_status.pop(previous_segment, None)
            self._voice_segments[speaker_id] = segment_id
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

    def _admit_voice(self, speaker_id: int) -> Optional[asyncio.Lock]:
        if (speaker_id not in self._embedding_attempts and len(self._embedding_attempts) >= MAX_SPEAKER_VOICES) or (
            speaker_id not in self._speaker_locks and len(self._speaker_locks) >= MAX_SPEAKER_VOICES
        ):
            self._record_exit('voice_capacity', speaker_id)
            return None
        self._embedding_attempts.setdefault(speaker_id, 0)
        return self._speaker_locks.setdefault(speaker_id, asyncio.Lock())

    def _reserve_embedding(self, speaker_id: int) -> bool:
        """Reserve synchronously before any await; failed requests spend tokens too."""
        now = time.monotonic()
        elapsed = max(0.0, now - self._socket_embedding_refilled_at)
        self._socket_embedding_tokens = min(
            SOCKET_EMBEDDING_BURST,
            self._socket_embedding_tokens + elapsed * SOCKET_EMBEDDING_REFILL_PER_SECOND,
        )
        self._socket_embedding_refilled_at = max(now, self._socket_embedding_refilled_at)
        if self._embedding_attempts[speaker_id] >= MAX_VOICE_EMBEDDING_ATTEMPTS or self._socket_embedding_tokens < 1:
            return False
        self._socket_embedding_tokens -= 1
        self._embedding_attempts[speaker_id] += 1
        return True

    async def match(self, speaker_id: int, segment: dict[str, Any]) -> None:
        conversation_id = self._profile_conversation_id
        if segment.get('conversation_id') is not None and segment['conversation_id'] != conversation_id:
            self._record_exit('stale_generation', speaker_id)
            return
        generation = self._generation
        lock = self._admit_voice(speaker_id)
        if lock is None:
            return
        self._lock_users[lock] = self._lock_users.get(lock, 0) + 1
        try:
            async with lock:
                drop_reason = self._drop_reason(generation, conversation_id, speaker_id)
                if drop_reason is not None:
                    if drop_reason == 'already_mapped':
                        await self._drop_rejected_mapping(speaker_id, segment, generation, conversation_id)
                    self._record_exit(drop_reason, speaker_id)
                    return
                await self._match_unmapped(speaker_id, segment, generation, conversation_id)
        finally:
            self._lock_users[lock] -= 1
            if self._lock_users[lock] == 0:
                del self._lock_users[lock]
                if generation != self._generation and self._speaker_locks.get(speaker_id) is lock:
                    del self._speaker_locks[speaker_id]

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
        final_authority = await self._final_authority(receipt)
        authority, receipt = final_authority.roster, final_authority.receipt
        if generation != self._generation or self._profile_conversation_id != conversation_id:
            return
        if not self._allow_authority_publication(final_authority, speaker_id=speaker_id, segment_id=segment.get('id')):
            return
        revoked = (
            self._mapping_origin.get(speaker_id) == 'automatic'
            and self.speaker_to_person.get(speaker_id, (None,))[0] == USER_SELF_PERSON_ID
            and sum(seconds for _, seconds in self.speaker_evidence.get(speaker_id, ()))
            < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
            and (self._voice_scopes.get(speaker_id, ''), speaker_id) not in authority[1]
        )
        if revoked or speaker_id in manual_rejected_speakers(receipt):
            self._retract_rejected_voice(speaker_id, segment.get('id'))
            if revoked and speaker_id in self._voice_decisions:
                self._voice_decisions[speaker_id] = replace(self._voice_decisions[speaker_id], person_id=None)
            self.host.state.speaker_map_dirty = True
        else:
            # Only buffered speech on the same scoped voice renews the gap.
            ring = getattr(self.host.state, 'audio_ring_buffer', None)
            bounds = ring.get_time_range() if ring is not None else None
            start, end = segment.get('abs_start'), segment.get('abs_end')
            if bounds and start is not None and end is not None and end > bounds[0] and start < bounds[1]:
                self.continuity.observe(speaker_id)
        await self.continuity.update(receipt, generation=generation)

    def _evidence_decision(
        self, voice: int, centroid: Any, distances: Dict[str, float], *, qualified_owner: bool = False
    ) -> SpeakerMatchDecision:
        decision = select_speaker_match(distances)
        if voice in self._competition_only:
            return replace(decision, person_id=None)
        seconds = sum(duration for _, duration in self.speaker_evidence.get(voice, ()))
        if seconds < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS and not (
            seconds >= FRESH_SECONDS and decision.person_id == USER_SELF_PERSON_ID and qualified_owner
        ):
            return replace(decision, person_id=None)
        return decision

    async def _final_authority(
        self,
        receipt: Mapping[str, Any],
        *,
        include_short: bool = False,
        receipt_unavailable: bool = False,
        rollover_donor: Optional[str] = None,
    ) -> FinalSpeakerAuthority:
        if (
            rollover_donor
            or include_short
            or any(
                sum(seconds for _, seconds in self.speaker_evidence.get(voice, ())) < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
                for voice in self._voice_centroids
            )
        ):
            authority, snapshots = await self.continuity.authorize_roster(
                self._profile_conversation_id or '', rollover_donor=rollover_donor
            )
            if snapshots is not None:
                current = snapshots.get(self._profile_conversation_id or '')
                unavailable = current is None
                # Failed/missing authority supplies no positive short proof.
                # Keep known receiving corrections rather than substituting an
                # empty reservation receipt that would protect stale manual maps.
                return FinalSpeakerAuthority(
                    (False, set()) if unavailable else authority,
                    receipt if current is None else current,
                    snapshots.get(rollover_donor) if rollover_donor else None,
                    unavailable=unavailable,
                )
            return FinalSpeakerAuthority(authority, receipt, unavailable=receipt_unavailable)
        return FinalSpeakerAuthority((False, set()), receipt, unavailable=receipt_unavailable)

    def _allow_authority_publication(
        self,
        authority: FinalSpeakerAuthority,
        *,
        speaker_id: Optional[int] = None,
        segment_id: Optional[str] = None,
    ) -> bool:
        """One gate for manual, automatic, carried and shortened publications.

        An unavailable final read grants only the independently known negative
        authority. Apply those retractions, then stop before identity or cache
        publication; an earlier positive receipt cannot authorize either.
        Callers must fence the matcher generation before entering this gate.
        """
        rejected = manual_rejected_speakers(authority.receipt)
        for voice in rejected:
            self._retract_rejected_voice(voice, segment_id if voice == speaker_id else self._voice_segments.get(voice))
        if rejected:
            self.host.state.speaker_map_dirty = True
        return not authority.unavailable

    def _rebuild_voice_decisions(self, authority: tuple[bool, set[tuple[str, int]]]) -> set[int]:
        """Recompute the current roster after the final authority await, without yielding."""
        hint_authorized, proofs = authority
        qualified = set()
        for voice, centroid in self._voice_centroids.items():
            evidence = self.speaker_evidence.get(voice, ())
            if evidence and voice not in self._competition_only:
                centroid = mean_embedding([vector for vector, _ in evidence])
            distances = {}
            for person_id, value in self.person_embeddings.items():
                vector = validated_embedding(value.get('embedding'))
                if vector is not None and vector.size == centroid.size:
                    distances[person_id] = compare_embeddings(centroid, vector)
            qualified_owner = (self._voice_scopes.get(voice, ''), voice) in proofs or (
                hint_authorized and self.continuity.matches(centroid, select_speaker_match(distances))
            )
            if qualified_owner:
                qualified.add(voice)
            self._voice_centroids[voice] = centroid
            self._voice_distances[voice] = distances
            self._voice_decisions[voice] = self._evidence_decision(
                voice, centroid, distances, qualified_owner=qualified_owner
            )
        return qualified

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

    def _manual_voice_decision(
        self, receipt: Mapping, speaker_id: int, *, scope: Optional[str] = None
    ) -> Optional[Mapping]:
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
        decision_scope = decision.get('speaker_id_scope')
        voice_scope = self._voice_scopes.get(speaker_id) if scope is None else scope
        if decision.get('source') == 'carried' and decision_scope is not None and decision_scope != voice_scope:
            return None
        return decision

    async def _match_unmapped(
        self, speaker_id: int, segment: dict[str, Any], generation: int, conversation_id: Optional[str]
    ) -> None:
        short_reconnect = False
        reconnect_recorded = False
        try:
            ring_buffer: Optional[AudioRingBuffer] = self.host.state.audio_ring_buffer
            if ring_buffer is None:
                self._record_exit('no_pcm', speaker_id)
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
                self._record_exit(
                    (
                        'segment_shorter_than_minimum'
                        if segment['duration'] < self.host.limits.speaker_id_min_audio
                        else 'window_outside_buffer'
                    ),
                    speaker_id,
                )
                return
            # Streaming providers resend/extend merged segments. Subtract every
            # successfully embedded interval before choosing a fresh clip, so an
            # update cannot turn three seconds of speech into six seconds of evidence.
            covered = [(a, b) for a, b in self._covered_audio.get(speaker_id, []) if b > buffer_start]
            self._covered_audio[speaker_id] = covered
            # Retain interval metadata only; PCM stays in the bounded ring.
            # Coalesce provider repeats before subtracting successful evidence.
            incoming = (
                max(buffer_start, segment['abs_start']),
                min(buffer_end, segment['abs_end'], segment['abs_start'] + max(0.0, segment['duration'])),
            )
            ranges = self._pending_audio.get(speaker_id, []) + [incoming]
            fresh = []
            for start, end in sorted(ranges):
                start, end = max(start, buffer_start), min(end, buffer_end)
                if end <= start:
                    continue
                if fresh and start <= fresh[-1][1]:
                    fresh[-1] = (fresh[-1][0], max(fresh[-1][1], end))
                else:
                    fresh.append((start, end))
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
            # A metadata cap also bounds pathological alternating tiny turns.
            self._pending_audio[speaker_id] = fresh[-128:]
            fresh = self._pending_audio[speaker_id]
            # Appending evicts the oldest clip. Gate against only the evidence
            # that will survive, or rejection can leave this voice pending forever.
            retained = list(self.speaker_evidence.get(speaker_id, ()))
            if speaker_id in self._competition_only and speaker_id not in self._competition_fresh:
                retained = []
            if len(retained) >= SPEAKER_MATCH_MAX_CLIPS:
                retained = retained[-(SPEAKER_MATCH_MAX_CLIPS - 1) :]
            have_seconds = sum(seconds for _, seconds in retained)
            reconnect_attempt = speaker_id not in self.continuity.attempted and self.continuity.available()
            evidence_floor = FRESH_SECONDS if reconnect_attempt else SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
            needed = max(0.5, min(self.host.limits.speaker_id_min_audio, evidence_floor - have_seconds))
            if sum(end - start for start, end in fresh) < needed:
                self._record_exit('window_shorter_than_minimum', speaker_id)
                return
            selected = []
            chunks = []
            remaining_seconds = MAX_SPEAKER_EMBEDDING_AUDIO_SECONDS
            for start, end in fresh:
                if remaining_seconds <= 0:
                    break
                if end - start > remaining_seconds:
                    # Preserve the existing centered query for a long turn;
                    # shorter disjoint intervals still pool without their gaps.
                    center = (start + end) / 2
                    start, end = center - remaining_seconds / 2, center + remaining_seconds / 2
                chunk = ring_buffer.extract(start, end)
                if not chunk:
                    continue
                chunks.append(chunk)
                selected.append((start, end))
                remaining_seconds -= end - start
            pcm = b''.join(chunks)
            if not pcm:
                self._record_exit('no_pcm', speaker_id)
                return
            clip_seconds = len(pcm) / (2 * self.host.request.sample_rate)
            if clip_seconds < needed:
                self._record_exit('window_shorter_than_minimum', speaker_id)
                return
            if not self._reserve_embedding(speaker_id):
                self._record_exit('embedding_budget', speaker_id)
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
            covered.extend(selected)
            self._pending_audio.pop(speaker_id, None)
            evidence = self.speaker_evidence.setdefault(speaker_id, deque(maxlen=SPEAKER_MATCH_MAX_CLIPS))
            if speaker_id in self._competition_only and speaker_id not in self._competition_fresh:
                evidence.clear()
                self._competition_fresh.add(speaker_id)
            evidence.append((query, clip_seconds))
            evidence_seconds = sum(seconds for _, seconds in evidence)
            if evidence_seconds < evidence_floor:
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
            distances = {}
            for person_id, value in self.person_embeddings.items():
                vector = validated_embedding(value.get('embedding'))
                if vector is not None and vector.size == centroid.size:
                    distances[person_id] = compare_embeddings(centroid, vector)
            query_decision = self._evidence_decision(speaker_id, centroid, distances)
            short_reconnect = evidence_seconds < SPEAKER_MATCH_MIN_EVIDENCE_SECONDS
            if short_reconnect:
                self.continuity.attempted.add(speaker_id)
                record_owner_reconnect('attempted', 'acoustic')
            # Keep the query row local through all receipt/authority awaits.
            # Other voices may arbitrate while we wait; every shared distance
            # row must already have its paired decision, even on cancellation.
            owner_reserved = False
            rejected: Dict[int, dict] = {}
            receipt: Mapping[str, Any] = {}
            receipt_unavailable = False
            if conversation_id:
                try:
                    receipt = await self.host.persistence.call(
                        conversations_db.get_manual_speaker_receipt, self.host.request.uid, conversation_id
                    )
                    owner_reserved = manual_owner_reserved(receipt)
                    rejected = manual_rejected_speakers(receipt)
                except Exception as error:
                    logger.warning('Speaker ID receipt load failed type=%s', type(error).__name__)
                    receipt_unavailable = True
            final_authority = await self._final_authority(
                receipt, include_short=short_reconnect, receipt_unavailable=receipt_unavailable
            )
            authority, receipt = final_authority.roster, final_authority.receipt
            owner_reserved = final_authority.owner_reserved
            rejected = manual_rejected_speakers(receipt)
            if (drop_reason := self._drop_reason(generation, conversation_id, speaker_id)) is not None:
                self._record_exit(drop_reason, speaker_id)
                return
            if not self._allow_authority_publication(final_authority, speaker_id=speaker_id, segment_id=segment['id']):
                self._record_exit('authority_unavailable', speaker_id)
                return
            if speaker_id in rejected:
                self._record_match_score(
                    speaker_id,
                    query_decision,
                    'manual_rejected',
                    distances=distances,
                    scope=segment.get('speaker_id_scope') or '',
                )
                self._record_exit('rejected', speaker_id)
                return
            manual = self._manual_voice_decision(receipt, speaker_id, scope=segment.get('speaker_id_scope') or '')
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
                self._voice_scopes[speaker_id] = segment.get('speaker_id_scope') or ''
                self._voice_segments[speaker_id] = segment['id']
                # Retain manual voices' acoustic competition too, but only
                # install the coherent row after any person-name lookup await.
                self._voice_centroids[speaker_id] = centroid
                self._voice_distances[speaker_id] = distances
                self._voice_decisions[speaker_id] = query_decision
                self._record_match_score(
                    speaker_id,
                    query_decision,
                    'manual_decision',
                    manual,
                    distances=distances,
                    scope=segment.get('speaker_id_scope') or '',
                )
                self._record_exit('manual_decision', speaker_id)
                return
            if (drop_reason := self._drop_reason(generation, conversation_id, speaker_id)) is not None:
                self._record_exit(drop_reason, speaker_id)
                return
            if not short_reconnect:
                self._competition_only.discard(speaker_id)
                self._competition_fresh.discard(speaker_id)
            previous_segment = self._voice_segments.get(speaker_id)
            if previous_segment and previous_segment not in self.segment_assignments:
                self.segment_identity_status.pop(previous_segment, None)
            self._voice_segments[speaker_id] = segment['id']
            self._voice_centroids[speaker_id] = centroid
            self._voice_scopes[speaker_id] = segment.get('speaker_id_scope') or ''
            self._rebuild_voice_decisions(authority)
            self.continuity.observe(speaker_id)
            voice_groups = self._provider_epoch_voice_groups()
            decisions = arbitrate_owner_matches(
                {v: d for v, d in self._voice_distances.items() if v not in rejected},
                {v: d for v, d in self._voice_decisions.items() if v not in rejected},
                owner_reserved=owner_reserved,
                voice_groups=voice_groups,
            )
            decision = decisions.get(speaker_id)
            decision_kind = 'rejected'
            if decision is not None:
                decision_target, decision_kind = live_decision_labels(
                    decision, owner_enrolled=USER_SELF_PERSON_ID in self.person_embeddings
                )
                if owner_near_miss(decision):
                    decision_kind = 'pending'
                record_live_speaker_decision(decision_target, decision_kind)
            logger.info(
                'speaker_id_decision surface=live speaker=%s clips=%d evidence_seconds=%.1f '
                'best=%s best_distance=%.3f runner_up_distance=%.3f accepted=%s owner_contended=%s decision=%s '
                'session=%s conversation=%s',
                speaker_id,
                len(evidence),
                evidence_seconds,
                decision.best_id if decision else None,
                decision.best_distance if decision else 0.0,
                decision.runner_up_distance if decision else 0.0,
                decision.accepted if decision else False,
                decision.owner_contended if decision else False,
                decision_kind,
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
            self._publish_decisions(decisions)
            if short_reconnect:
                accepted = decision is not None and decision.person_id == USER_SELF_PERSON_ID
                if accepted:
                    self.continuity.remember_accept(speaker_id)
                record_owner_reconnect(
                    'accepted' if accepted else 'rejected',
                    (
                        'accepted'
                        if accepted
                        else ('arbitration' if decision and decision.owner_contended else 'acoustic')
                    ),
                )
                reconnect_recorded = True
            await self.continuity.update(receipt, force=True, generation=generation)
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
        finally:
            if short_reconnect and not reconnect_recorded:
                record_owner_reconnect('rejected', 'arbitration')

    def _publish_decisions(self, decisions: Mapping[int, SpeakerMatchDecision]) -> None:
        decisions = {
            voice: replace(decision, person_id=None) if voice in self._competition_only else decision
            for voice, decision in decisions.items()
        }
        prior = pinned_speaker_prior_enabled()
        pinned = {pid for pid, value in self.person_embeddings.items() if value.get('pinned')}
        assigned = {result.person_id for result in decisions.values() if result.person_id is not None}
        for voice, result in decisions.items():
            if self._mapping_origin.get(voice) == 'manual':
                continue
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
                if changed and segment_id != '':
                    self.host.emit_speaker_suggestion(voice, best_id, best_name, segment_id)
            else:
                # Completed-roster revalidation can abstain on an ordinary
                # margin rejection as well as owner contention. Neither may
                # leave an earlier automatic accept in the assignment map.
                was_mapped = self.speaker_to_person.pop(voice, None)
                self._mapping_origin.pop(voice, None)
                if was_mapped and segment_id != '':
                    self.host.emit_speaker_suggestion(voice, '', '', segment_id, retracted=True)
                if result.owner_contended:
                    if self.voice_identity_status.get(voice) != SpeakerIdentityStatus.ambiguous:
                        logger.info(
                            'speaker_id_owner_contention surface=live speaker=%s session=%s',
                            voice,
                            self._session_log_id(),
                        )
                status = (
                    SpeakerIdentityStatus.ambiguous
                    if result.owner_contended
                    else SpeakerIdentityStatus.unknown if owner_near_miss(result) else SpeakerIdentityStatus.no_match
                )
                if prior:
                    self._offer_pinned_suggestion(voice, result, pinned, segment_id, assigned)
            self._record_match_score(voice, result)
            self.voice_identity_status[voice] = status
            self.segment_identity_status[segment_id] = status
        self.host.state.speaker_map_dirty = True
        self.host.state.speaker_map_version = getattr(self.host.state, 'speaker_map_version', 0) + 1

    def _record_match_score(
        self,
        voice: int,
        decision: SpeakerMatchDecision,
        outcome: Optional[str] = None,
        manual: Optional[Mapping] = None,
        *,
        distances: Optional[Mapping[str, float]] = None,
        scope: Optional[str] = None,
    ) -> None:
        try:
            if match_scores.enabled():
                row = match_scores.summarize(
                    voice,
                    self._voice_distances[voice] if distances is None else distances,
                    decision,
                    sum(seconds for _, seconds in self.speaker_evidence[voice]),
                    'capture',
                    threshold=match_policy.SPEAKER_MATCH_THRESHOLD,
                    margin_threshold=match_policy.SPEAKER_MATCH_MARGIN,
                    scope=self._voice_scopes.get(voice, '') if scope is None else scope,
                    outcome=outcome,
                )
                if outcome is None and owner_near_miss(decision):
                    row['status'] = 'unknown'
                    row['decision'] = 'pending'
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
        # Retire idle locks now, held/waited locks only after their last user
        # finishes. New-generation work for that voice stays serialized; every
        # old-generation await still fences publication into the new inventory.
        self._speaker_locks = {
            voice: lock for voice, lock in self._speaker_locks.items() if self._lock_users.get(lock, 0)
        }
        self._covered_audio.clear()
        self._pending_audio.clear()
        self._embedding_attempts.clear()
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
        self._competition_only.clear()
        self._competition_fresh.clear()
        self._voice_segments.clear()
        self._voice_centroids.clear()
        self._voice_scopes.clear()
        self.voice_candidates.clear()
        self.match_scores.clear()
        self._suggested_person.clear()
