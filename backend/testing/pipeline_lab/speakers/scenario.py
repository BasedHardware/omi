"""Speakers in scenario mode: the hosted diarizer as a loopback peer, an enrolled gallery, and staged units.

A scenario with a ``speakers`` block (``scenario/spec.py``) runs the product's speaker code instead of the lab's
cassette-label stand-in:

1. **Peer.** Before the lab environment, :meth:`ScenarioSpeakers.start` starts a :class:`~.peer.SpeakerPeer`
   (``--speakers replay``, the default: cassettes only; ``record-local``: production's diarizer code on this CPU
   for a miss). Its URL goes into the product env as ``HOSTED_DIARIZATION_API_URL`` and
   ``HOSTED_SPEAKER_EMBEDDING_API_URL``, and its loopback port joins the lab network's allowed peers.
2. **Batch-lane diarization.** The batch lane's worker diarizes each unit through the product's own client
   (``utils.stt.diarization.HttpDiarizer``, ``POST /v2/diarization`` with the unit's PCM): production's
   community-1 turns, not turns implied by cassette word labels. Projection then runs with the unit as its
   batch scope (``final:batch:<unit>``), the way the production projector calls it, and the recording's stored
   segments are the projection's own segments (ids, scopes, provider markers).
3. **Gallery.** :meth:`seed_gallery` embeds each enrollment WAV through the product's
   ``extract_embedding_from_bytes`` (``POST /v2/embedding`` to the peer) and writes it with product writers:
   the owner's vector with ``users.set_user_speaker_embedding``; each enrolled person with ``create_person``,
   ``add_person_speech_sample``, ``update_person_speech_samples_version(3)`` and
   ``set_person_speaker_embedding`` (the shape ``usable_person_voiceprint`` accepts). Naming people is a paid
   entitlement (``named_speaker_prompts_allowed``), so with enrolled people the lab account gets a paid plan
   through ``users.update_user_subscription``.
4. **Staged units** (the stand-in). Production's speaker passes rebuild a conversation's audio from the batch
   pipeline's store: ``database.batch_final_pass.load_reference`` (job, result receipts, artifact rows, privacy
   fence) and the encrypted artifacts (``artifacts.load_result``, ``artifacts.fetch_audio``). The lab never
   writes that store, so :meth:`install` answers those three reads from the units this run's batch lane
   produced (the worker's result payload and the unit's WAV), and replaces the store handle
   (``FirestoreStore``) the lab's ``local`` stage cannot build. Everything around them is product code:
   ``batch_identity_evidence.load`` (per-label clips, ``voice_centroids.extract``, embeddings through the peer),
   ``resolve_conversation_speakers``, ``apply_speaker_resolution``, and the whole-conversation
   ``run_batch_final_pass`` (``HttpDiarizer`` to the peer, ``run_final_pass``). The stand-in keeps production's
   receipt rule: a unit's projection receipt names the conversation the projection wrote it to (the recording),
   and ``load_reference`` for any other conversation id answers ``skipped_merged`` as production's does. A
   scenario may set ``speakers.receipts: "processed"``, a counterfactual reported as such, under which the receipt
   names the conversation the speaker pass runs on (the v3 conversation), so the rest of the chain is measured.

What ran and what did not is counted and reported in the run's ``speakers`` block and stand-in notes.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import time
from typing import Any, Mapping, Optional
from unittest.mock import patch

from testing.pipeline_lab.speakers.peer import MODES, SpeakerPeer
from testing.pipeline_lab.scenario.paths import private_lab_root
from testing.pipeline_lab.speakers.peer import CassetteStore
from testing.pipeline_lab.store import ensure_private_dir
from utils.stt.diarization import HttpDiarizer
from utils.stt.speaker_embedding import extract_embedding_from_bytes
from database import batch_final_pass
from database.batch_final_pass import ReferenceUnavailable
from testing.pipeline_lab.speakers.corpus import PUBLIC_ROOT
import json
from testing.pipeline_lab.speakers.score import score_conversation

DEFAULT_MODE = 'replay'
OWNER = 'user'
PLAN = 'unlimited'  # a paid plan: naming enrolled people is a paid entitlement
DIARIZE_DEADLINE_SECONDS = 900.0  # record-local runs the model on CPU


@dataclass
class LabUnit:
    """One batch unit the lab's batch lane produced: what production's staged store would hold for it."""

    item: Any  # utils.batch_pipeline.contracts.WorkItem
    binding: Any  # ProjectionBinding
    policy: Any  # config.policy.ProjectionPolicy
    payload: dict
    wav: bytes
    receipt_conversation_id: str  # the conversation the projection wrote this unit to (the recording)

    @property
    def uri(self) -> str:
        return f'lab-result://{self.item.segment_id}#lab'


@dataclass
class ScenarioSpeakers:
    """The run's speaker peer, gallery and staged units. Built before the lab environment (the peer's cassette
    root and record mode need the ambient environment), used inside it."""

    mode: str
    peer: Optional[SpeakerPeer]
    gallery: Mapping[str, str] = field(default_factory=dict)  # identity -> enrollment WAV path
    units: dict[str, LabUnit] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, int] = field(default_factory=dict)  # speaker_resolution.resolver_reason
    final_pass: list[str] = field(default_factory=list)  # run_batch_final_pass outcomes, in order
    seeded: dict[str, Any] = field(default_factory=dict)
    receipts: str = 'recording'  # whom unit receipts name: the recording (production) or the processed conversation

    @classmethod
    def start(
        cls, spec: Any, mode: str = DEFAULT_MODE, *, audio_files: tuple = (), peer: Optional[SpeakerPeer] = None
    ) -> 'ScenarioSpeakers':
        """Start the peer under the ambient environment. Cassettes recorded for audio that is all committed and
        public (``speakers/fixtures`` or ``scenario/fixtures``) go to the committed cassette directory; any other
        audio records under the private lab root. In ``record-local`` the model worker starts here, while the
        environment still names the local-models venv and its model cache."""
        if mode not in MODES:
            raise ValueError(f'--speakers must be one of {MODES}')
        if peer is None and spec.peer:
            public = all(_public(Path(path)) for path in (*audio_files, *spec.gallery.values()))
            store = workdir = None
            if public and mode == 'record-local':

                root = ensure_private_dir(private_lab_root() / 'speakers')
                store = CassetteStore(ensure_private_dir(root / 'cassettes'), write_public=True)
                workdir = ensure_private_dir(ensure_private_dir(private_lab_root() / 'tmp') / 'speakers')
            peer = SpeakerPeer(mode, store=store, workdir=workdir)
            if mode == 'record-local' and peer.local is not None:
                peer.local.idle.append(peer.local._start())  # noqa: SLF001 - under the ambient env, not the lab's
            peer.start()
        return cls(mode=mode, peer=peer, gallery=dict(spec.gallery), receipts=spec.receipts)

    def stop(self) -> None:
        if self.peer is not None:
            self.peer.stop()

    # ---- environment -----------------------------------------------------------------------------

    def env(self) -> dict[str, str]:
        return self.peer.env() if self.peer is not None else {}

    def ports(self) -> tuple[int, ...]:
        if self.peer is None or self.peer.server is None:
            return ()
        return (int(self.peer.server.server_address[1]),)

    def _count(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    # ---- batch lane ------------------------------------------------------------------------------

    def diarize(self, pcm16: bytes) -> dict[str, Any]:
        """One unit through the product's hosted-diarizer client: the worker's diarization payload shape."""

        result = HttpDiarizer('pyannote').diarize(pcm16, deadline=time.monotonic() + DIARIZE_DEADLINE_SECONDS)
        self._count('batch_lane_diarizations')
        value = result.model_dump()
        return {'turns': value.get('turns') or [], 'overlaps': value.get('overlaps') or [], 'backend': 'pyannote'}

    def register_unit(self, unit: LabUnit) -> None:
        self.units[unit.item.segment_id] = unit

    # ---- gallery ---------------------------------------------------------------------------------

    def seed_gallery(self, uid: str, now: datetime) -> dict[str, Any]:
        """Embed and enroll every gallery voice through product code. Returns counts (no vectors)."""
        from database import users as users_db
        from utils.stt.owner_profile import validated_embedding

        enrolled: dict[str, Any] = {}
        people = [label for label in self.gallery if label != OWNER]
        if people:
            users_db.update_user_subscription(
                uid,
                {
                    'plan': PLAN,
                    'status': 'active',
                    'current_period_end': int((now + timedelta(days=30)).timestamp()),
                },
            )
        for label, path in sorted(self.gallery.items()):
            wav = Path(path).read_bytes()
            vector = validated_embedding(extract_embedding_from_bytes(wav, f'{label}.wav', use_cache=False))
            self._count('gallery_embeddings')
            if vector is None:
                raise RuntimeError(f'gallery {label}: the embedding the peer returned is not a usable voiceprint')
            values = [float(v) for v in vector.reshape(-1)]
            if label == OWNER:
                users_db.set_user_speaker_embedding(uid, values)
            else:
                stamp = now.astimezone(timezone.utc)
                users_db.create_person(
                    uid, {'id': label, 'name': _display_name(label), 'created_at': stamp, 'updated_at': stamp}
                )
                users_db.add_person_speech_sample(uid, label, f'{uid}/people/{label}/sample-0.wav')
                users_db.update_person_speech_samples_version(uid, label, 3)
                person = users_db.get_person(uid, label) or {}
                if not users_db.set_person_speaker_embedding(
                    uid, label, values, expected_updated_at=person.get('updated_at')
                ):
                    raise RuntimeError(f'gallery {label}: the product refused the voiceprint write')
            enrolled[label] = {'dimension': len(values), 'audio_sha256': hashlib.sha256(wav).hexdigest()[:12]}
        self.seeded = {'enrolled': enrolled, 'plan': PLAN if people else None}
        return self.seeded

    # ---- staged-unit stand-in --------------------------------------------------------------------

    def install(self, stack: ExitStack) -> None:

        # The product's ownership rule; a tree from before it (compare against an older ref) owns only its own id.
        receipt_owners = getattr(batch_final_pass, 'receipt_owners', None) or (lambda cid, source_ids=(): {cid})
        from utils.conversations import final_pass_batch, speaker_resolution

        speakers = self

        def load_reference(
            store: Any, uid: str, unit: str, conversation_id: str, *, read_budget: Any = None, source_ids: Any = ()
        ):
            speakers._count('stand_in_load_reference')
            lab = speakers.units.get(unit)
            if lab is None or lab.item.owner_id != uid:
                raise ReferenceUnavailable('failed_incomplete_coverage', 'no_job')
            if speakers.receipts == 'processed':
                speakers._count('stand_in_load_reference_counterfactual')  # the receipt names this conversation
            elif lab.receipt_conversation_id not in receipt_owners(conversation_id, source_ids):
                # Production's rule over the receipts the projection wrote for this unit: they name another
                # conversation, so this one is a merge target (database/batch_final_pass.py).
                speakers._count('stand_in_load_reference_skipped_merged')
                raise ReferenceUnavailable('skipped_merged')
            return lab.item, lab.uri, lab.binding, lab.policy

        class Artifacts:
            def load_result(self, item: Any, uri: str, *, read_budget: Any = None, **_: Any) -> dict:
                speakers._count('stand_in_load_result')
                return speakers.units[item.segment_id].payload

            def fetch_audio(self, item: Any, *, read_budget: Any = None, **_: Any) -> bytes:
                speakers._count('stand_in_fetch_audio')
                return speakers.units[item.segment_id].wav

        class Store:
            def __init__(self, namespace: str, **_: Any):
                self.namespace = namespace

        original_pass = final_pass_batch.run_batch_final_pass
        original_reason = speaker_resolution.resolver_reason

        def run_batch_final_pass(*args: Any, **kwargs: Any) -> Any:
            result = original_pass(*args, **kwargs)
            speakers.final_pass.append(str((result or {}).get('outcome')))
            return result

        def resolver_reason(reason: str) -> None:
            speakers.reasons[reason] = speakers.reasons.get(reason, 0) + 1
            return original_reason(reason)

        stack.enter_context(patch.object(final_pass_batch, 'load_reference', load_reference))
        stack.enter_context(patch.object(final_pass_batch, 'artifacts_for', lambda store, **_: Artifacts()))
        stack.enter_context(patch.object(final_pass_batch, 'FirestoreStore', Store))
        stack.enter_context(patch.object(final_pass_batch, 'current_stage', lambda: 'lab'))
        stack.enter_context(patch.object(final_pass_batch, 'run_batch_final_pass', run_batch_final_pass))
        stack.enter_context(patch.object(speaker_resolution, 'resolver_reason', resolver_reason))

    # ---- report ----------------------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        peer = self.peer.stats.summary() if self.peer is not None else {}
        return {
            'mode': self.mode,
            'peer': bool(self.peer),
            'gallery': sorted(self.gallery),
            'seeded': self.seeded,
            'units': len(self.units),
            'counts': dict(sorted(self.counts.items())),
            'resolver_reasons': dict(sorted(self.reasons.items())),
            'final_pass': list(self.final_pass),
            'receipts': self.receipts,
            # hit / miss / recorded per route: cassette provenance (a record-mode repeat replays what the first
            # run recorded), so determinism.SCENARIO_ARTIFACTS drops it like ``cassette_origin``.
            'cassette_outcomes': peer,
        }


def _public(path: Path) -> bool:

    scenario_fixtures = Path(__file__).resolve().parents[1] / 'scenario' / 'fixtures'
    resolved = path.resolve()
    return any(root in resolved.parents for root in (PUBLIC_ROOT, scenario_fixtures))


@dataclass
class SpeakerScoring:
    """Scores a conversation's persisted segments against the scenario's speaker truth (numbers only)."""

    truth: dict
    words: list[dict]  # the recording's cassette words, on its audio clock
    audio_start: datetime  # the recording's first sample, as an instant
    label: str  # the recording the truth is on
    final_pass: list = field(default_factory=list)  # the run's run_batch_final_pass outcomes (shared list)

    @classmethod
    def for_scenario(cls, scenario: Any, prepared: Mapping[str, Any]) -> 'SpeakerScoring':

        spec = scenario.speakers
        rec = scenario.recording(spec.recording)
        item = prepared.get(rec.label)
        words = [{'start': w.start, 'end': w.end, 'text': w.text} for w in item.cassette.words] if item else []
        truth = json.loads(Path(spec.truth).read_text(encoding='utf-8'))
        return cls(truth=truth, words=words, audio_start=scenario.at(rec.audio[0]), label=rec.label)

    def card(self, row: Mapping[str, Any]) -> Optional[dict[str, Any]]:
        """The scorecard for one stored conversation row, or None when it has no started_at."""

        started = row.get('started_at')
        if isinstance(started, str):
            try:
                started = datetime.fromisoformat(started.replace('Z', '+00:00'))
            except ValueError:
                return None
        if not isinstance(started, datetime):
            return None
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        shift = (started - self.audio_start).total_seconds()
        turns = []
        for segment in row.get('transcript_segments') or []:
            try:
                start, end = float(segment['start']) + shift, float(segment['end']) + shift
            except (KeyError, TypeError, ValueError):
                continue
            turns.append(
                {
                    'start': start,
                    'end': end,
                    'speaker': segment.get('speaker'),
                    'speaker_id': segment.get('speaker_id'),
                    'speaker_id_scope': segment.get('speaker_id_scope'),
                    'is_user': bool(segment.get('is_user')),
                    'person_id': segment.get('person_id'),
                }
            )
        card = score_conversation(self.words, self.truth, turns)
        keys = (
            'attribution', 'owner_precision', 'owner_recall', 'named_accuracy', 'named_coverage', 'wrong_name_rate',
        )  # fmt: skip
        return {
            **{key: card[key] for key in keys},
            'owner_words': card['owner_claimed'],
            'words': card['words'],
            'voices': card['predicted_voices'],
            'truth_voices': card['truth_voices'],
            # The last whole-pass outcome of the run: a scorecard the resolver alone satisfied must not hide a
            # failing final pass.
            'final_pass': self.final_pass[-1] if self.final_pass else None,
            # What the stored ids mean (models.conversation.ConversationSpeakers.status): the app numbers voices
            # ("Speaker 1", "Speaker 2") only for a resolved conversation.
            'resolution': (row.get('speaker_resolution') or {}).get('status'),
        }


def _display_name(label: str) -> str:
    """A synthetic display name from the gallery label (``person-a`` -> ``Person A``)."""
    return ' '.join(part.capitalize() for part in label.replace('_', '-').split('-') if part) or label
