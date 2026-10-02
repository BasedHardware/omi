"""Bounded durable ledger for manual speaker-teaching jobs.

One document per conversation at ``users/{uid}/speaker_learning_jobs/{conversation_id}``
holds a bounded map of jobs; every read is a direct document get — no queries,
no index changes. A job is committed atomically with the label that authorizes
it (assignment transaction) or at first explicit deferral (``ensure_job``), is
claimed under a short lease by the coordinator, and finishes against the same
publication fences the extractors already use. Deterministic job ids make
duplicate delivery a no-op; expired leases are reclaimed by the next trigger.
"""

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.speaker_profile_authority import owner_teaching_authorized, person_teaching_authorized
from models.other import VoiceReadiness, voice_readiness
from models.person_confidence import SOURCE_CARD
from utils.observability.speaker_learning_jobs import record_speaker_learning_job_events
from utils.owner_voice_evidence import authorized_owner_segments
from utils.speaker_learning_policy import authorized_teaching_segments

MAX_JOBS = 32
MAX_SEGMENT_IDS = 200
MAX_ATTEMPTS = 5
JOB_LIFETIME = timedelta(days=7)
LEASE_DURATION = timedelta(minutes=2)
RETRY_DELAYS = (30, 120, 600, 3600)
RETRYABLE_OUTCOMES = frozenset(
    {
        'no_audio',
        'no_chunks',
        'uncovered_audio',
        'transcription_failed',
        'embedding_failed',
        'transient_failure',
        'timeout',
        'error',
    }
)

JOB_EVENTS_KEY = '_speaker_learning_job_events'
JOB_QUEUED_KEY = '_speaker_learning_queued'

_TERMINAL_OUTCOMES = frozenset(
    {
        'stored',
        'exhausted',
        'superseded',
        'deleted',
        'locked',
        'discarded',
        'disabled',
        'capacity_exhausted',
        'segment_limit',
        'text_mismatch',
        'insufficient_speech',
        'insufficient_words',
        'multi_speaker',
        'contaminated',
        'clip_not_clean',
        'rejected_quality',
        'rejected_embedding',
    }
)
_KNOWN_OUTCOMES = RETRYABLE_OUTCOMES | _TERMINAL_OUTCOMES

_NORMALIZED_OUTCOMES = {
    'missing': 'deleted',
    'person_missing': 'deleted',
    'conversation_missing': 'deleted',
    'stale_assignment': 'superseded',
    'no_authorized_segments': 'superseded',
}

_PUBLIC_TERMINAL_STATES = {
    'disabled': 'disabled',
    'insufficient_speech': 'needs_more_speech',
}


def extract_learning_receipt_markers(receipt: dict, current: dict) -> None:
    """Move the assignment transaction's transient job markers onto the in-memory result."""
    events = receipt.pop(JOB_EVENTS_KEY, [])
    current[JOB_EVENTS_KEY] = events
    current[JOB_QUEUED_KEY] = any(outcome == 'queued' for _, outcome in events)


def jobs_ref(user_ref: Any, conversation_id: str) -> Any:
    return user_ref.collection('speaker_learning_jobs').document(conversation_id)


def _client(firestore_client: Any) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


def _job_id(target: str, person_id: Optional[str], generation: Any, segment_ids: Any, card_generation: Any) -> str:
    payload = json.dumps(
        [target, person_id, generation, sorted(segment_ids or []), card_generation],
        separators=(',', ':'),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _new_job(
    conversation_id: str,
    target: str,
    person_id: Optional[str],
    generation: Any,
    segment_ids: list,
    card_generation: Any,
    now: datetime,
) -> dict:
    return {
        'conversation_id': conversation_id,
        'target': target,
        'person_id': person_id,
        'generation': generation,
        'segment_ids': list(segment_ids),
        'card_generation': card_generation,
        'attempts': 0,
        'last_outcome': None,
        'state': 'pending',
        'next_attempt_at': now,
        'lease_token': None,
        'lease_until': None,
        'created_at': now,
        'expires_at': now + JOB_LIFETIME,
    }


def _transition_terminal(job: dict, outcome: str) -> None:
    job['state'] = 'terminal'
    job['last_outcome'] = outcome
    job['next_attempt_at'] = None
    job['lease_token'] = None
    job['lease_until'] = None


def _source_status(conversation: Optional[Mapping[str, Any]]) -> Optional[str]:
    if not conversation or conversation.get('deleted'):
        return 'deleted'
    if conversation.get('is_locked'):
        return 'locked'
    if conversation.get('discarded'):
        return 'discarded'
    return None


def _normalize_outcome(outcome: Any) -> str:
    mapped = _NORMALIZED_OUTCOMES.get(outcome, outcome)
    return mapped if mapped in _KNOWN_OUTCOMES else 'error'


def _finite_nonzero_vector(vector: Any) -> bool:
    return (
        isinstance(vector, list)
        and bool(vector)
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in vector)
        and any(v != 0 for v in vector)
    )


def _person_stored(person: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    if voice_readiness(person) != VoiceReadiness.ready:
        return False
    source = person.get('speech_sample_source') or {}
    if source.get('conversation_id') != job.get('conversation_id'):
        return False
    ids = source.get('segment_ids') or []
    if not ids or not set(ids) <= set(job.get('segment_ids') or []):
        return False
    stored_at = _as_utc(source.get('stored_at'))
    created = _as_utc(job.get('created_at'))
    if stored_at is None or created is None or stored_at < created:
        return False
    generation = source.get('generation')
    job_generation = job.get('generation')
    if (
        not isinstance(generation, int)
        or not isinstance(job_generation, int)
        or isinstance(generation, bool)
        or generation < job_generation
    ):
        return False
    return True


def _owner_stored(user_doc: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    if not _finite_nonzero_vector(user_doc.get('speaker_embedding')):
        return False
    created = _as_utc(job.get('created_at'))
    card = job.get('card_generation')
    job_generation = job.get('generation')
    for item in user_doc.get('owner_voice_confirmations') or []:
        if not isinstance(item, Mapping) or item.get('conversation_id') != job.get('conversation_id'):
            continue
        ids = item.get('segment_ids') or []
        if not ids or not set(ids) <= set(job.get('segment_ids') or []):
            continue
        at = _as_utc(item.get('at'))
        if at is None or created is None or at < created:
            continue
        generation = item.get('generation')
        if card is not None:
            if generation != card:
                continue
        elif (
            not isinstance(generation, int)
            or isinstance(generation, bool)
            or not isinstance(job_generation, int)
            or isinstance(job_generation, bool)
            or generation < job_generation
        ):
            continue
        return True
    return False


def _gather(transaction: Any, user_ref: Any, uid: str, conversation_id: str, jobs: Mapping[str, dict]) -> tuple:
    conversation = user_ref.collection('conversations').document(conversation_id).get(transaction=transaction).to_dict()
    user_doc = user_ref.get(transaction=transaction).to_dict() or {}
    people = {
        pid: user_ref.collection('people').document(pid).get(transaction=transaction).to_dict()
        for pid in {
            job.get('person_id') for job in jobs.values() if job.get('target') == 'person' and job.get('person_id')
        }
    }
    return conversation, user_doc, people


def _authority_check(
    transaction: Any, user_ref: Any, uid: str, conversation_id: str, user_doc: Mapping, people: Mapping
) -> Callable[[Mapping[str, Any]], Optional[str]]:
    def check(job: Mapping[str, Any]) -> Optional[str]:
        if job.get('target') == 'person':
            person = people.get(job.get('person_id'))
            if person is None:
                return 'deleted'
            if not user_doc.get('save_other_voice_profiles', True):
                return 'disabled'
            if not person_teaching_authorized(
                transaction,
                user_ref,
                job['person_id'],
                uid,
                conversation_id,
                job.get('segment_ids') or [],
                job.get('generation'),
            ):
                return 'superseded'
            if _person_stored(person, job):
                return 'stored'
            return None
        if not owner_teaching_authorized(
            transaction,
            user_ref,
            uid,
            conversation_id,
            job.get('segment_ids'),
            job.get('generation'),
            job.get('card_generation'),
        ):
            return 'superseded'
        if _owner_stored(user_doc, job):
            return 'stored'
        return None

    return check


def _reconcile_jobs(
    jobs: dict,
    *,
    source_status: Optional[str],
    now: datetime,
    check: Callable[[Mapping[str, Any]], Optional[str]],
) -> list:
    events = []
    for job in jobs.values():
        if job.get('state') == 'terminal':
            continue
        lease_until = _as_utc(job.get('lease_until'))
        active = job.get('state') == 'running' and lease_until is not None and lease_until > now
        outcome = source_status or check(job)
        if outcome is None and not active:
            expires = _as_utc(job.get('expires_at'))
            if (expires is not None and expires <= now) or int(job.get('attempts') or 0) >= MAX_ATTEMPTS:
                outcome = 'exhausted'
        if outcome is not None:
            _transition_terminal(job, outcome)
            events.append((job.get('target') or 'person', outcome))
    return events


def _admit(jobs: dict, job_id: str, job: dict, events: list) -> None:
    if len(jobs) >= MAX_JOBS:
        for victim_id in sorted(
            (jid for jid, j in jobs.items() if j.get('state') == 'terminal'),
            key=lambda jid: _as_utc(jobs[jid].get('created_at')) or datetime.min.replace(tzinfo=timezone.utc),
        ):
            del jobs[victim_id]
            if len(jobs) < MAX_JOBS:
                break
    if len(jobs) >= MAX_JOBS:
        victim_id = min(
            jobs,
            key=lambda jid: _as_utc(jobs[jid].get('created_at')) or datetime.min.replace(tzinfo=timezone.utc),
        )
        events.append((jobs[victim_id].get('target') or 'person', 'capacity_exhausted'))
        del jobs[victim_id]
    jobs[job_id] = job


def _person_state_update(
    user_doc: Mapping[str, Any], person: Optional[Mapping[str, Any]], job: Mapping[str, Any], job_id: str
) -> Optional[dict]:
    """The public state write a job transition earns, or None when the pointer moved on."""
    if job.get('target') != 'person' or person is None:
        return None
    pointer = person.get('voice_learning_job') or {}
    if pointer.get('job_id') != job_id or pointer.get('conversation_id') != job.get('conversation_id'):
        return None
    if not user_doc.get('save_other_voice_profiles', True):
        state = 'disabled'
    elif voice_readiness(person) == VoiceReadiness.ready:
        state = 'learned'
    elif job.get('state') == 'terminal':
        outcome = job.get('last_outcome')
        state = _PUBLIC_TERMINAL_STATES.get(outcome, 'unknown') if isinstance(outcome, str) else 'unknown'
    else:
        state = 'pending'
    update = {'voice_learning_state': state, 'voice_learning_outcome': job.get('last_outcome')}
    if state != 'needs_more_speech':
        update['voice_needed_seconds'] = None
    return update


def _ledger_transaction(
    client: Any,
    uid: str,
    conversation_id: str,
    now: datetime,
    body: Callable[
        [
            Any,
            dict,
            Callable[[Mapping[str, Any]], Optional[str]],
            Optional[str],
            Any,
            Mapping,
            Mapping,
            Any,
            list,
            list,
        ],
        bool,
    ],
) -> dict:
    """Read the ledger world, run ``body``, reconcile, and stage writes — reads first.

    ``body(transaction, jobs, check, source_status, conversation, user_doc,
    people, user_ref, writes, events)`` mutates ``jobs``, appends ``(ref, update)`` extra document
    writes to ``writes`` and ``(target, outcome)`` pairs to ``events``; it returns
    True when the ledger doc itself changed. Every transactional read happens
    before the first staged write; counter events are emitted post-commit only.
    """
    user_ref = client.collection('users').document(uid)
    ref = jobs_ref(user_ref, conversation_id)
    events: list = []
    result: dict = {}

    @firestore.transactional
    def txn(transaction: Any) -> None:
        del events[:]
        result.clear()
        snapshot = ref.get(transaction=transaction)
        ledger = snapshot.to_dict() or {}
        jobs = dict(ledger.get('jobs') or {})
        conversation, user_doc, people = _gather(transaction, user_ref, uid, conversation_id, jobs)
        check = _authority_check(transaction, user_ref, uid, conversation_id, user_doc, people)
        source_status = _source_status(conversation)
        events.extend(_reconcile_jobs(jobs, source_status=source_status, now=now, check=check))
        writes: list = []
        dirty = body(transaction, jobs, check, source_status, conversation, user_doc, people, user_ref, writes, events)
        events.extend(_reconcile_jobs(jobs, source_status=source_status, now=now, check=check))
        for doc_ref, update in writes:
            transaction.update(doc_ref, update)
        if dirty or events:
            transaction.set(ref, {'jobs': jobs})
        result.update(jobs=jobs, user_doc=user_doc, people=people, conversation=conversation)

    run_transactional(client, txn)
    record_speaker_learning_job_events(events)
    return result


def ensure_job(
    uid: str,
    conversation_id: str,
    *,
    person_id: Optional[str],
    segment_ids: list,
    card_generation: Optional[int] = None,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Optional[str]:
    """Persist the deferred job if its authorization still holds; return its id or None."""
    client = _client(firestore_client)
    now = now or _now()
    target = 'person' if person_id else 'owner'
    segment_ids = [sid for sid in (segment_ids or []) if isinstance(sid, str) and sid]
    if not segment_ids:
        return None
    ensured: dict = {}

    def body(transaction, jobs, check, source_status, conversation, user_doc, people, user_ref, writes, events) -> bool:
        ensured.clear()
        if source_status is not None:
            return False
        from database.conversations import decode_manual_speaker_assignments

        receipt = decode_manual_speaker_assignments(
            uid,
            (conversation or {}).get('manual_speaker_assignments'),
            bool((conversation or {}).get('manual_speaker_assignments_compressed')),
        )
        generation = receipt.get('generation', 0)
        job_id = _job_id(target, person_id, generation, segment_ids, card_generation)
        existing = jobs.get(job_id)
        if existing is not None:
            return False
        wanted = set(segment_ids)
        decision_generation = 0
        try:
            from database.conversations import decode_transcript_segments_verified

            decoded = (
                decode_transcript_segments_verified(
                    uid,
                    (conversation or {}).get('transcript_segments') or [],
                    bool((conversation or {}).get('transcript_segments_compressed')),
                )
                or []
            )
        except Exception:
            decoded = []
        from utils.speaker_learning_policy import winning_receipt_decision

        for segment in decoded:
            if segment.get('id') not in wanted:
                continue
            decision = winning_receipt_decision(receipt, segment)
            decision_gen = (decision or {}).get('generation')
            if isinstance(decision_gen, int) and not isinstance(decision_gen, bool):
                decision_generation = max(decision_generation, decision_gen)
        for prior in jobs.values():
            if (
                not isinstance(prior, Mapping)
                or prior.get('target') != target
                or prior.get('person_id') != person_id
                or prior.get('card_generation') != card_generation
            ):
                continue
            prior_generation = prior.get('generation')
            if (
                not isinstance(prior_generation, int)
                or isinstance(prior_generation, bool)
                or prior_generation > generation
                or prior_generation < decision_generation
            ):
                continue
            if wanted <= set(prior.get('segment_ids') or []) and check(prior) in (None, 'stored'):
                return False
        person_ref = user_ref.collection('people').document(person_id) if person_id else None
        person = person_ref.get(transaction=transaction).to_dict() if person_ref is not None else None
        if person is not None:
            people[person_id] = person
        if target == 'person':
            if person is None or not isinstance(person_id, str) or not user_doc.get('save_other_voice_profiles', True):
                return False
            if not person_teaching_authorized(
                transaction, user_ref, person_id, uid, conversation_id, segment_ids, generation
            ):
                return False
        else:
            if not owner_teaching_authorized(
                transaction, user_ref, uid, conversation_id, segment_ids, generation, card_generation
            ):
                return False
        if len(segment_ids) > MAX_SEGMENT_IDS:
            job = _new_job(
                conversation_id, target, person_id, generation, segment_ids[:MAX_SEGMENT_IDS], card_generation, now
            )
            _transition_terminal(job, 'segment_limit')
            _admit(jobs, job_id, job, events)
            events.append((target, 'segment_limit'))
            return True
        _admit(
            jobs,
            job_id,
            _new_job(conversation_id, target, person_id, generation, segment_ids, card_generation, now),
            events,
        )
        events.append((target, 'queued'))
        ensured['job_id'] = job_id
        if person is not None:
            writes.append(
                (
                    person_ref,
                    {'voice_learning_job': {'conversation_id': conversation_id, 'job_id': job_id}},
                )
            )
        return True

    _ledger_transaction(client, uid, conversation_id, now, body)
    return ensured.get('job_id')


def claim_next_job(
    uid: str,
    conversation_id: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> Optional[dict]:
    """Reconcile the ledger and claim the oldest eligible job under a fresh lease."""
    client = _client(firestore_client)
    now = now or _now()
    claimed: dict = {}

    def body(transaction, jobs, check, source_status, conversation, user_doc, people, user_ref, writes, events) -> bool:
        claimed.clear()
        eligible = []
        for jid, job in jobs.items():
            if job.get('state') == 'pending':
                if (_as_utc(job.get('next_attempt_at')) or now) <= now:
                    eligible.append((jid, job))
            elif job.get('state') == 'running':
                if (_as_utc(job.get('lease_until')) or now) <= now:
                    eligible.append((jid, job))
        if not eligible:
            return False
        jid, job = min(
            eligible,
            key=lambda item: _as_utc(item[1].get('created_at')) or datetime.min.replace(tzinfo=timezone.utc),
        )
        job['attempts'] = int(job.get('attempts') or 0) + 1
        job['state'] = 'running'
        job['lease_token'] = uuid.uuid4().hex
        job['lease_until'] = now + LEASE_DURATION
        job['next_attempt_at'] = None
        if job['attempts'] > 1:
            events.append((job.get('target') or 'person', 'retried'))
        claimed.update(dict(job, job_id=jid))
        update = _person_state_update(user_doc, people.get(job.get('person_id')), job, jid)
        if update is not None:
            writes.append((user_ref.collection('people').document(job['person_id']), update))
        return True

    _ledger_transaction(client, uid, conversation_id, now, body)
    return dict(claimed) if claimed else None


def finish_job(
    uid: str,
    conversation_id: str,
    job_id: str,
    lease_token: str,
    outcome: str,
    *,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> bool:
    """Record the claimed attempt's outcome; a stale lease token is a no-op."""
    client = _client(firestore_client)
    now = now or _now()
    applied: dict = {'done': False}
    normalized = _normalize_outcome(outcome)

    def body(transaction, jobs, check, source_status, conversation, user_doc, people, user_ref, writes, events) -> bool:
        applied['done'] = False
        job = jobs.get(job_id)
        if job is None or job.get('lease_token') != lease_token:
            return False
        final = source_status or check(job) or normalized
        attempts = int(job.get('attempts') or 0)
        job['lease_token'] = None
        job['lease_until'] = None
        if final in RETRYABLE_OUTCOMES:
            expires = _as_utc(job.get('expires_at'))
            if attempts >= MAX_ATTEMPTS or (expires is not None and expires <= now):
                final = 'exhausted'
            else:
                job['state'] = 'pending'
                job['last_outcome'] = final
                job['next_attempt_at'] = now + timedelta(seconds=RETRY_DELAYS[attempts - 1])
                applied['done'] = True
                update = _person_state_update(user_doc, people.get(job.get('person_id')), job, job_id)
                if update is not None:
                    writes.append((user_ref.collection('people').document(job['person_id']), update))
                return True
        _transition_terminal(job, final)
        events.append((job.get('target') or 'person', final))
        applied['done'] = True
        update = _person_state_update(user_doc, people.get(job.get('person_id')), job, job_id)
        if update is not None:
            writes.append((user_ref.collection('people').document(job['person_id']), update))
        return True

    _ledger_transaction(client, uid, conversation_id, now, body)
    return applied['done']


def prepare_assignment_jobs(
    transaction: Any,
    user_ref: Any,
    conversation_id: str,
    conversation: Mapping[str, Any],
    resolved: list,
    *,
    person_id: Optional[str],
    is_user: bool,
    use_for_speech_training: bool,
    evidence_source: str,
    user_doc: Mapping[str, Any],
    people: Mapping[str, Any],
    updates: dict,
    now: datetime,
    owner_segment_ids: Optional[list] = None,
) -> tuple:
    """Stage the ledger write inside the assignment transaction.

    Reads the ledger (plus person docs live jobs reference) before any write and
    validates existing jobs against the already-decoded updated conversation —
    the persisted receipt still reads old inside this transaction, so the
    transactional authority helpers cannot be used here. Queues the job this
    assignment earns and returns ``(ref, payload, events)``; ``payload`` is
    None when nothing changed.
    """
    ref = jobs_ref(user_ref, conversation_id)
    snapshot = ref.get(transaction=transaction)
    ledger = snapshot.to_dict() or {}
    jobs = dict(ledger.get('jobs') or {})
    receipt = conversation.get('manual_speaker_assignments') or {}
    segments = conversation.get('transcript_segments') or []
    policy_conversation = {'transcript_segments': segments, 'manual_speaker_assignments': receipt}
    save_other = bool(user_doc.get('save_other_voice_profiles', True))
    people_docs = dict(people)
    extra_ids = {
        job.get('person_id') for job in jobs.values() if job.get('target') == 'person' and job.get('person_id')
    } - set(people_docs)
    for pid in extra_ids:
        people_docs[pid] = user_ref.collection('people').document(pid).get(transaction=transaction).to_dict()

    def person_allowed(pid: str) -> set:
        if receipt.get('segments') or receipt.get('speakers'):
            return {s.get('id') for s in authorized_teaching_segments(policy_conversation, pid)}
        return {s.get('id') for s in segments if s.get('person_id') == pid and not s.get('is_user')}

    def check(job: Mapping[str, Any]) -> Optional[str]:
        if job.get('target') == 'person':
            pid = job.get('person_id')
            if not isinstance(pid, str):
                return 'deleted'
            person = people_docs.get(pid)
            if person is None:
                return 'deleted'
            if not save_other:
                return 'disabled'
            if not set(job.get('segment_ids') or []) <= person_allowed(pid):
                return 'superseded'
            if _person_stored(person, job):
                return 'stored'
            return None
        allowed = set(
            authorized_owner_segments(
                policy_conversation, job.get('segment_ids') or [], card_generation=job.get('card_generation')
            )
        )
        if allowed != set(job.get('segment_ids') or []):
            return 'superseded'
        if _owner_stored(user_doc, job):
            return 'stored'
        return None

    source_status = _source_status(conversation)
    events = _reconcile_jobs(jobs, source_status=source_status, now=now, check=check)
    generation = receipt.get('generation', 0)
    new_ids: list = []
    card_generation: Optional[int] = None
    target: Optional[str] = None
    if person_id:
        target = 'person'
        if use_for_speech_training and save_other:
            allowed = person_allowed(person_id)
            new_ids = [sid for sid in resolved if sid in allowed]
    elif is_user:
        target = 'owner'
        if evidence_source == SOURCE_CARD and not use_for_speech_training:
            card_generation = generation
            wanted = [sid for sid in dict.fromkeys(owner_segment_ids or []) if sid in set(resolved)]
            granted = set(authorized_owner_segments(policy_conversation, wanted, card_generation=card_generation))
            new_ids = [sid for sid in wanted if sid in granted]
        elif use_for_speech_training:
            granted = set(authorized_owner_segments(policy_conversation, resolved))
            new_ids = [sid for sid in resolved if sid in granted]
    dirty = bool(events)
    if target and new_ids:
        job_id = _job_id(target, person_id if target == 'person' else None, generation, new_ids, card_generation)
        if job_id not in jobs:
            if source_status is not None:
                job = _new_job(
                    conversation_id, target, person_id, generation, new_ids[:MAX_SEGMENT_IDS], card_generation, now
                )
                _transition_terminal(job, source_status)
                _admit(jobs, job_id, job, events)
                events.append((target, source_status))
            elif len(new_ids) > MAX_SEGMENT_IDS:
                job = _new_job(
                    conversation_id, target, person_id, generation, new_ids[:MAX_SEGMENT_IDS], card_generation, now
                )
                _transition_terminal(job, 'segment_limit')
                _admit(jobs, job_id, job, events)
                events.append((target, 'segment_limit'))
            else:
                _admit(
                    jobs,
                    job_id,
                    _new_job(conversation_id, target, person_id, generation, new_ids, card_generation, now),
                    events,
                )
                events.append((target, 'queued'))
            dirty = True
        if target == 'person' and person_id:
            pointer = {'conversation_id': conversation_id, 'job_id': job_id}
            current_pointer = (people_docs.get(person_id) or {}).get('voice_learning_job') or {}
            if current_pointer != pointer:
                updates.setdefault(person_id, {})['voice_learning_job'] = pointer
    if not dirty:
        return ref, None, events
    return ref, {'jobs': jobs}, events


def project_person_learning(
    uid: str,
    person: dict,
    *,
    firestore_client: Any = None,
    now: Optional[datetime] = None,
) -> dict:
    """Project the durable ledger onto a person's public learning state.

    ``pending`` requires a still-existing, still-authorized, runnable job;
    terminal outcomes map onto the existing public enum (stored + usable
    profile → learned, disabled → disabled, true shortage → needs_more_speech,
    everything else → unknown). Reconciliation may atomically terminalize an
    expired or revoked job; no provider call ever runs here.
    """
    if not person:
        return person
    pointer = person.get('voice_learning_job') or {}
    job_id = pointer.get('job_id')
    conversation_id = pointer.get('conversation_id')
    if not job_id or not conversation_id:
        data = dict(person)
        if data.get('voice_learning_state') != 'disabled' and voice_readiness(data) == VoiceReadiness.ready:
            data['voice_learning_state'] = 'learned'
        elif data.get('voice_learning_state') in (None, 'pending', 'learned'):
            data['voice_learning_state'] = 'unknown'
        if data.get('voice_learning_state') != 'needs_more_speech':
            data['voice_needed_seconds'] = None
        return data
    client = _client(firestore_client)
    result = _ledger_transaction(client, uid, conversation_id, now or _now(), _read_only_body)
    user_doc = result.get('user_doc') or {}
    fresh = (result.get('people') or {}).get(person.get('id')) or person
    fresh_pointer = fresh.get('voice_learning_job') or {}
    job = None
    if fresh_pointer.get('job_id') == job_id and fresh_pointer.get('conversation_id') == conversation_id:
        candidate = (result.get('jobs') or {}).get(job_id)
        if (
            candidate is not None
            and candidate.get('target') == 'person'
            and candidate.get('person_id') == person.get('id')
        ):
            job = candidate
    data = dict(fresh)
    data.setdefault('id', person.get('id'))
    if not user_doc.get('save_other_voice_profiles', True):
        state = 'disabled'
    elif voice_readiness(fresh) == VoiceReadiness.ready:
        state = 'learned'
    elif job is not None and job.get('state') != 'terminal':
        state = 'pending'
    elif job is not None:
        outcome = job.get('last_outcome')
        state = _PUBLIC_TERMINAL_STATES.get(outcome, 'unknown') if isinstance(outcome, str) else 'unknown'
    else:
        state = 'unknown'
    data['voice_learning_state'] = state
    if state != 'needs_more_speech':
        data['voice_needed_seconds'] = None
    return data


def _read_only_body(
    transaction, jobs, check, source_status, conversation, user_doc, people, user_ref, writes, events
) -> bool:
    return False
