"""Additional acoustic verification for a recent same-account/install owner.

Never blend donor evidence into a query, reuse diarizer ids, or replenish a
handoff from a shortened accept. Enrollment and joint arbitration remain the
identity authority. All persisted vectors are encrypted by the cache adapter.
"""

import asyncio
import hashlib
import time
import uuid
from typing import Any, Optional

import numpy as np

from database import live_owner_continuity as cache
from utils.executors import db_executor, run_blocking
from utils.manual_speaker_assignments import manual_owner_reserved, manual_rejected_speakers
from utils.observability.owner_recognition import record_owner_reconnect
from utils.stt.owner_profile import validated_embedding

FRESH_SECONDS = 2.0
# Stricter than the existing 0.50 cross-provider voice grouping boundary.
SESSION_DISTANCE = 0.35


def profile_digest(vector: Any) -> str:
    return hashlib.sha256(np.asarray(vector, dtype=np.float32).reshape(-1).tobytes()).hexdigest()


class OwnerContinuity:
    def __init__(self, matcher: Any):
        self.matcher = matcher
        host = matcher.host
        self.uid = getattr(getattr(host, 'request', None), 'uid', None)
        self.device = getattr(getattr(host, 'client_device_context', None), 'client_device_id', None)
        self.token = str(uuid.uuid4())
        self.started = False
        self.donor: Optional[dict[str, Any]] = None
        self._lock = asyncio.Lock()
        self._last_write = 0.0
        self._published = False
        self._published_observed_at = 0.0
        self.attempted: set[int] = set()
        self.observed: dict[tuple[str, int], float] = {}

    async def start(self) -> None:
        if self.started:
            return
        self.started = True
        if not self.uid:
            return
        record_owner_reconnect('attempted', 'lookup')
        if not self.device:
            record_owner_reconnect('rejected', 'no_device')
            return
        self.donor, reason = await run_blocking(db_executor, cache.begin, self.uid, self.device, self.token)
        if self.donor is None:
            record_owner_reconnect('rejected', reason)

    def available(self) -> bool:
        owner = self.matcher.person_embeddings.get('user')
        donor = self.donor
        if donor is None:
            return False
        try:
            valid = (
                owner is not None
                and 0 <= time.time() - float(donor['observed_at']) <= cache.GAP_SECONDS
                and donor['profile'] == profile_digest(owner['embedding'])
                and float(donor['seconds']) >= 5.0
                and validated_embedding(donor['centroid']) is not None
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            self.donor = None
            record_owner_reconnect('rejected', 'expired_or_profile')
        return valid

    def matches(self, centroid: Any, decision: Any) -> bool:
        from utils.stt.speaker_embedding import compare_embeddings

        if not self.available():
            return False
        donor = self.donor
        if donor is None:
            return False
        vector = validated_embedding(donor['centroid'])
        return bool(
            vector is not None
            and vector.size == centroid.size
            and decision.person_id == 'user'
            and compare_embeddings(centroid, vector) < SESSION_DISTANCE
        )

    def observe(self, voice: int) -> None:
        scope = self.matcher._voice_scopes.get(voice)
        if scope:
            self.observed[(scope, voice)] = time.time()
            # Same bounded voice inventory as the matcher; no unbounded epochs.
            if len(self.observed) > 128:
                self.observed.pop(next(iter(self.observed)))

    def refresh_due(self) -> bool:
        return (
            self._published
            and time.monotonic() - self._last_write >= 30.0
            and max(self.observed.values(), default=0.0) > self._published_observed_at
        )

    async def refresh(self) -> None:
        """The matcher queue deliberately skips mapped voices; refresh on its idle tick."""
        from utils.transcribe_store import conversations_db

        if not self.refresh_due():
            return
        matcher = self.matcher
        generation, conversation = matcher._generation, matcher._profile_conversation_id
        if not conversation:
            return
        # Bound even failed receipt reads to one per 30 seconds.
        self._last_write = time.monotonic()
        try:
            receipt = await matcher.host.persistence.call(
                conversations_db.get_manual_speaker_receipt, self.uid, conversation
            )
        except Exception:
            return
        await self.update(receipt, force=True, generation=generation)

    async def update(self, receipt: Any, *, force: bool = False, generation: Optional[int] = None) -> None:
        """Refresh recent speech only from an independently accepted >=5s owner.

        The receipt is from the current match/read, never a persisted prediction.
        Serialize this socket's publications as well as fencing other sockets.
        """
        if not self.started or not self.uid or not self.device:
            return
        async with self._lock:
            matcher = self.matcher
            if generation is not None and generation != matcher._generation:
                return
            owner = matcher.person_embeddings.get('user')
            blocked = getattr(matcher.host.request, 'owner_persistence_blocked', None)
            epoch = getattr(getattr(matcher.host, 'receiver', None), 'speaker_provider_epoch', None)
            active_scope = getattr(epoch, 'current_scope', None)
            voices = [
                voice
                for voice, identity in matcher.speaker_to_person.items()
                if identity[0] == 'user'
                and matcher._mapping_origin.get(voice) == 'automatic'
                and (active_scope is None or matcher._voice_scopes.get(voice) == active_scope)
                and voice not in manual_rejected_speakers(receipt)
                and matcher._manual_voice_decision(receipt, voice) is None
                and sum(seconds for _, seconds in matcher.speaker_evidence.get(voice, ())) >= 5.0
                and voice in matcher._voice_centroids
            ]
            payload: Optional[dict[str, Any]] = None
            if owner and len(voices) == 1 and not manual_owner_reserved(receipt) and not (blocked and blocked.is_set()):
                voice = voices[0]
                payload = {
                    'v': 1,
                    'device': self.device,
                    'profile': profile_digest(owner['embedding']),
                    'centroid': matcher._voice_centroids[voice].reshape(-1).tolist(),
                    'seconds': sum(seconds for _, seconds in matcher.speaker_evidence[voice]),
                    'observed_at': self.observed.get((matcher._voice_scopes.get(voice, ''), voice), 0.0),
                }
                if not 0 <= time.time() - payload['observed_at'] <= cache.GAP_SECONDS:
                    payload = None
            now = time.monotonic()
            if payload is not None and not force and self._published and now - self._last_write < 30.0:
                return
            if payload is None and not self._published:
                return
            self._last_write, self._published = now, payload is not None
            self._published_observed_at = payload['observed_at'] if payload else 0.0
            await run_blocking(db_executor, cache.publish, self.uid, self.device, self.token, payload)
