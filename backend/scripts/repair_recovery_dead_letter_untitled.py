#!/usr/bin/env python3
"""Repair bound, recovery-dead-lettered untitled conversations without processing.

Dry-run by default. --apply is an operator-only write mode. --rollback also
requires --apply to write. New runs require a fresh --run-dir; --resume retains
its original mode and cohort. --limit bounds newly evaluated jobs per invocation.

Audit field states are Fernet-encrypted with the local audit.key (0600), including
missing-field information. Keep that key with audit.jsonl for rollback. The
append-only audit is a write-ahead decision log; results.jsonl records outcomes.
An interrupted commit is reconciled using the entire expected after-row digest,
never retried blindly. Cursor checkpoints advance only after a page drains;
processed IDs cover crashes mid-page. Errors remain retryable on resume.

Calendar safety protects nonempty rule discards: stored overlaps and connected
Google Calendar accounts skip without provider calls/token-refresh writes. Empty
transcript rule discards bypass calendars; photos and every other fence remain.
Kept titles require nonempty text; protected rule discards never receive titles.
Summary breakdowns group R/K and protected/empty skips by source, rule and summed
audio_files.duration seconds: 0, (0,5), [5,30), [30,120], >120, or unknown.
Missing/invalid duration metadata is unknown, never inferred from capture time.
Calendar lookup errors are unclassifiable. Photo subcollections are checked even on
legacy rows. Only Typesense converges after successful writes, like the existing
discard_by_relevance choke point; finalization job counters remain unchanged.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import fcntl
import importlib
import json
import logging
import math
import os
from pathlib import Path
import random
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, Callable, Iterable
import uuid

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from cryptography.fernet import Fernet
from google.api_core.exceptions import Aborted, Conflict, DeadlineExceeded, ServiceUnavailable
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from models.conversation_enums import ConversationSource
from scripts.conversation_relevance_backfill import AUDIO_TRANSCRIPT_SOURCES
from utils.conversations.deterministic_minimum import deterministic_minimum_title
from utils.conversations.fragment_visibility import is_user_curated
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import structured_has_protected_content, structured_is_rich
from utils.conversations.relevance import RelevanceDecision
from utils.conversations.relevance_rules import deterministic_relevance
from utils.conversations.wake_word import find_wake_word_matches
from utils.release_probe import is_release_probe_uid

JOBS = 'conversation_finalization_jobs'
JOB_FILTERS = {
    'last_failure_code': 'recovery_structure_unavailable',
    'status': 'dead_letter',
    'processing_trigger': 'server_recovery',
}
ALLOWED_FIELDS = {'discarded', 'relevance_decision', 'structured.title'}
RETRYABLE = (Aborted, Conflict, DeadlineExceeded, ServiceUnavailable)
AUDIO_DURATION_BUCKETS = ('0', '<5s', '5-30s', '30-120s', '>120s', 'unknown')
BREAKDOWN_CATEGORIES = ('R', 'K', 'discard_protected', 'empty_not_discardable')
logger = logging.getLogger('untitled_repair')
_decode_state = threading.local()


class CannotClassify(Exception):
    """Only bounded reason codes escape data-reading helpers."""

    def __init__(self, reason: str, *, rule: str | None = None):
        super().__init__(reason)
        self.rule = rule


def audio_duration_bucket(row: dict[str, Any]) -> str:
    """Use stored audio duration only; partial or malformed totals are unknown."""
    audio_files = row.get('audio_files')
    if not isinstance(audio_files, list):
        return 'unknown'
    durations = []
    for audio_file in audio_files:
        duration = audio_file.get('duration') if isinstance(audio_file, dict) else None
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            return 'unknown'
        try:
            seconds = float(duration)
        except OverflowError:
            return 'unknown'
        if not math.isfinite(seconds) or seconds < 0:
            return 'unknown'
        durations.append(seconds)
    try:
        total = math.fsum(durations)
    except OverflowError:
        return 'unknown'
    if total == 0:
        return '0'
    if total < 5:
        return '<5s'
    if total < 30:
        return '5-30s'
    if total <= 120:
        return '30-120s'
    return '>120s'


def summary_source(row: dict[str, Any]) -> str:
    """Never expose arbitrary stored source strings as summary/audit labels."""
    source = row.get('source')
    return ConversationSource(source).value if isinstance(source, str) else 'unknown'


class PrivateHelperLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            _decode_state.failed = True
        # Legacy decrypt/index helpers log full UIDs and exception payloads.
        # Their output must not reach any handler (including an operator's).
        return False


def install_private_log_filters() -> None:
    for name in ('utils.encryption', 'database.conversations', 'utils.conversations.typesense_index'):
        logging.getLogger(name).addFilter(PrivateHelperLogs())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    def encode(obj: Any) -> Any:
        if isinstance(obj, bytes):
            return {'bytes': obj.hex()}
        if isinstance(obj, datetime):
            return {'datetime': obj.isoformat()}
        raise TypeError(type(obj).__name__)

    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode).encode()).hexdigest()


def safe_id(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(f'{uid}:{conversation_id}'.encode()).hexdigest()[:20]


def valid_binding(job: dict[str, Any]) -> bool:
    return all(isinstance(job.get(key), str) and job[key] and '/' not in job[key] for key in ('uid', 'conversation_id'))


def eligibility(row: dict[str, Any] | None, job_id: str, job: dict[str, Any]) -> str | None:
    if not valid_binding(job):
        return 'invalid_job_binding'
    if any(job.get(k) != v for k, v in JOB_FILTERS.items()):
        return 'job_not_candidate'
    if is_release_probe_uid(job['uid']):
        return 'release_probe'
    if row is None:
        return 'missing_conversation'
    if row.get('deleted'):
        return 'deleted'
    if row.get('status') != 'completed':
        return 'not_completed'
    if row.get('discarded') is not False:
        return 'not_visible'
    if row.get('finalization_status') != 'dead_letter':
        return 'not_dead_letter'
    if row.get('finalization_job_id') != job_id:
        return 'job_binding_changed'
    structured = row.get('structured')
    if not isinstance(structured, dict):
        return 'invalid_structure'
    if structured_is_rich(structured):
        return 'rich_structure'
    if not isinstance(structured.get('title', ''), str) or structured.get('title', '').strip():
        return 'nonempty_title'
    if row.get('user_title'):
        return 'user_title'
    if structured_has_protected_content(structured, row.get('user_title')):
        return 'protected_structure'
    if row.get('photos') or row.get('has_photos'):
        return 'photos'
    if row.get('sync_relevance_user_kept'):
        return 'user_kept'
    # Extra conservative fence: manual curation is evidence of user intent.
    if is_user_curated(row) or row.get('is_locked') or row.get('folder_id'):
        return 'user_curated'
    return None


def decode_transcript(row: dict[str, Any], uid: str) -> list[dict[str, Any]]:
    if row.get('data_protection_level') == 'e2ee':
        raise CannotClassify('e2ee')
    raw = row.get('transcript_segments')
    if raw is None:
        # Missing is not evidence of a captured empty transcript.
        raise CannotClassify('missing_transcript')
    if isinstance(raw, list):
        segments = raw
    else:
        if not os.environ.get('ENCRYPTION_SECRET') or len(os.environ['ENCRYPTION_SECRET']) < 32:
            raise CannotClassify('decryption_key_unavailable')
        _decode_state.failed = False
        try:
            module = importlib.import_module('database.conversations')
            decoded = module._decrypt_conversation_data(row, uid)
        except Exception:
            raise CannotClassify('transcript_decode_failed') from None
        if getattr(_decode_state, 'failed', False):
            raise CannotClassify('transcript_decode_failed')
        segments = decoded.get('transcript_segments')
    if not isinstance(segments, list) or any(
        not isinstance(s, dict) or not isinstance(s.get('text'), str) for s in segments
    ):
        raise CannotClassify('invalid_transcript')
    return segments


def get_field(row: dict[str, Any], path: str) -> dict[str, Any]:
    current: Any = row
    for part in path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return {'present': False}
        current = current[part]
    return {'present': True, 'value': current}


def patched(row: dict[str, Any], states: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(row)
    for path, state in states.items():
        target = result
        parts = path.split('.')
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        if state['present']:
            target[parts[-1]] = deepcopy(state['value'])
        else:
            target.pop(parts[-1], None)
    return result


class RateLimiter:
    def __init__(self, qps: float):
        self.interval = 1 / qps
        self.next_at = 0.0
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = max(0.0, self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval
        if delay:
            time.sleep(delay)


class RunLog:
    def __init__(self, path: Path, config: dict[str, Any], *, resume: bool = False):
        self.path = path
        self.lock = threading.Lock()
        if not path.is_absolute():
            raise ValueError('run directory must be absolute')
        if resume:
            self.config = json.loads((path / 'config.json').read_text())
            if self.config != config:
                raise ValueError('resume mode/cohort must match original run')
        else:
            path.mkdir(mode=0o700, parents=True, exist_ok=False)
            self.config = config
            self.save('config.json', config)
            fd = os.open(path / 'audit.key', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as file:
                file.write(Fernet.generate_key())
                file.flush()
                os.fsync(file.fileno())
        self.cipher = Fernet((path / 'audit.key').read_bytes())
        self.results = {r['decision_id']: r for r in self.read('results.jsonl')}
        self.processed = {r['job_id'] for r in self.results.values() if r['outcome'] != 'error'}
        state_path = path / 'checkpoint.json'
        self.cursor = json.loads(state_path.read_text()).get('cursor') if state_path.exists() else None

    def read(self, name: str) -> list[dict[str, Any]]:
        path = self.path / name
        return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []

    def save(self, name: str, value: Any) -> None:
        temporary = self.path / f'{name}.{uuid.uuid4().hex}.tmp'
        with temporary.open('x') as file:
            json.dump(value, file, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, self.path / name)

    def append(self, name: str, value: Any) -> None:
        with self.lock:
            with (self.path / name).open('a') as file:
                file.write(json.dumps(value, sort_keys=True) + '\n')
                file.flush()
                os.fsync(file.fileno())

    def seal(self, states: dict[str, Any]) -> str:
        return self.cipher.encrypt(json.dumps(states).encode()).decode()

    def unseal(self, token: str) -> dict[str, Any]:
        return json.loads(self.cipher.decrypt(token.encode()))

    def finish(self, record: dict[str, Any], outcome: str) -> None:
        result = {
            'decision_id': record['decision_id'],
            'job_id': record['job_id'],
            'outcome': outcome,
            'commit_revision': record.get('commit_revision'),
            'at': utc_now(),
        }
        self.append('results.jsonl', result)
        self.results[result['decision_id']] = result
        if outcome != 'error':
            self.processed.add(result['job_id'])

    def checkpoint(self, cursor: str) -> None:
        self.cursor = cursor
        self.save('checkpoint.json', {'cursor': cursor, 'processed_ids': sorted(self.processed)})


@dataclass
class Runtime:
    client: Any
    decode: Callable[[dict[str, Any], str], list[dict[str, Any]]] = decode_transcript
    protections: Callable[[Any, dict[str, Any], dict[str, Any], Any], str | None] | None = None
    converge: Callable[[str, str], Any] | None = None

    def protect(
        self,
        ref: Any,
        row: dict[str, Any],
        job: dict[str, Any],
        transaction: Any = None,
        *,
        include_calendar: bool = True,
    ) -> str | None:
        if self.protections is not None:
            protection = self.protections(ref, row, job, transaction)
            if not include_calendar and protection in ('calendar_overlap', 'calendar_connected_unverified'):
                return None
            return protection
        # Read queries before any write, including legacy subcollection photos.
        if list(ref.collection('photos').select([]).limit(1).stream(transaction=transaction)):
            return 'photos'
        if not include_calendar:
            return None
        start, end = row.get('started_at'), row.get('finished_at')
        if row.get('calendar_event') or (row.get('external_data') or {}).get('calendar_meeting_context'):
            return 'calendar_overlap'
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise CannotClassify('calendar_window_unknown')
        # Superset of capture-end's stored selector: retain any meeting in the
        # tolerance window. Avoid provider traffic and model imports altogether.
        meetings = self.client.collection('users').document(job['uid']).collection('meetings')
        if list(
            meetings.where(filter=FieldFilter('start_time', '<', end + timedelta(minutes=30)))
            .where(filter=FieldFilter('end_time', '>', start - timedelta(minutes=30)))
            .order_by('start_time')
            .limit(10)
            .stream(transaction=transaction)
        ):
            return 'calendar_overlap'
        integration = self.client.document(f"users/{job['uid']}/integrations/google_calendar").get(
            transaction=transaction
        )
        if integration.exists and (integration.to_dict() or {}).get('connected'):
            return 'calendar_connected_unverified'
        return None

    def timezone(self, uid: str) -> str | None:
        snapshot = self.client.document(f'users/{uid}').get()
        return (snapshot.to_dict() or {}).get('time_zone') if snapshot.exists else None

    def sync(self, job: dict[str, Any]) -> None:
        try:
            if self.converge is not None:
                self.converge(job['uid'], job['conversation_id'])
            else:
                module = importlib.import_module('utils.conversations.typesense_index')
                module.sync_conversation_index_after_write(
                    job['uid'], job['conversation_id'], firestore_client=self.client, db_client=self.client
                )
        except Exception:
            logger.warning('projection_sync_failed id=%s', safe_id(job['uid'], job['conversation_id']))


def classify(runtime: Runtime, row: dict[str, Any], job: dict[str, Any], ref: Any) -> tuple[str, str, dict[str, Any]]:
    # Check photo subcollections independently of calendar lookups. An empty
    # transcript must still be discardable when calendar reads are unavailable.
    protection = runtime.protect(ref, row, job, include_calendar=False)
    if protection == 'photos':
        raise CannotClassify('photos')
    segments = runtime.decode(row, job['uid'])
    texts = [s['text'] for s in segments]
    # Supply IDs for legacy segments so wake-word content cannot evade protection.
    wake_segments = [dict(s, id=s.get('id') or f'legacy-{i}') for i, s in enumerate(segments)]
    verdict, rule = deterministic_relevance(texts, None)
    if find_wake_word_matches(wake_segments):
        if verdict == 'discard':
            raise CannotClassify('discard_protected', rule=rule)
        verdict, rule = 'keep', 'wake_word'
    if verdict == 'discard':
        # External/workflow/screen imports can hold content outside transcripts;
        # the ordinary capture-end rule does not assess those source branches.
        if row.get('source') not in AUDIO_TRANSCRIPT_SOURCES:
            raise CannotClassify('non_audio_source', rule=rule)
        if rule != 'empty_transcript':
            protection = runtime.protect(ref, row, job)
        if protection == 'photos':
            raise CannotClassify('photos', rule=rule)
        if protection:
            raise CannotClassify('discard_protected', rule=rule)
    if verdict == 'discard':
        return (
            'R',
            rule,
            {
                'discarded': True,
                'relevance_decision': RelevanceDecision(
                    'discard', 'rule', rule, ProcessingTrigger.SERVER_RECOVERY
                ).as_record(),
            },
        )
    if not any(text.strip() for text in texts):
        raise CannotClassify('empty_not_discardable', rule=rule)
    conversation = SimpleNamespace(
        transcript_segments=[SimpleNamespace(**s) for s in segments], started_at=row.get('started_at')
    )
    return (
        'K',
        rule,
        {
            'structured.title': deterministic_minimum_title(
                conversation, tz_name_provider=lambda: runtime.timezone(job['uid'])
            )
        },
    )


def write_cas(
    runtime: Runtime,
    job_id: str,
    job: dict[str, Any],
    row: dict[str, Any],
    updates: dict[str, Any],
    row_revision: Any = None,
    job_revision: Any = None,
) -> dict[str, Any]:
    job_ref = runtime.client.collection(JOBS).document(job_id)
    ref = runtime.client.document(f"users/{job['uid']}/conversations/{job['conversation_id']}")

    @firestore.transactional
    def mutate(transaction: Any) -> str:
        job_snapshot = job_ref.get(transaction=transaction)
        current_job = job_snapshot.to_dict() or {}
        snapshot = ref.get(transaction=transaction)
        current = snapshot.to_dict() if snapshot.exists else None
        reason = eligibility(current, job_id, current_job)
        if reason:
            return reason
        assert current is not None
        if (
            current != row
            or current_job != job
            or getattr(snapshot, 'update_time', None) != row_revision
            or getattr(job_snapshot, 'update_time', None) != job_revision
        ):
            return 'cas_changed'
        discarding = updates.get('discarded') is True
        check_calendar = discarding and updates['relevance_decision']['reason'] != 'empty_transcript'
        protection = runtime.protect(ref, current, job, transaction, include_calendar=check_calendar)
        if protection == 'photos':
            return 'photos'
        if discarding and protection:
            return 'discard_protected'
        transaction.update(ref, updates)
        return 'written'

    transaction = runtime.client.transaction(max_attempts=1)
    outcome = mutate(transaction)
    results = getattr(transaction, '_write_results', [])
    revision = results[-1].update_time.isoformat() if results else None
    return {'outcome': outcome, 'commit_revision': revision}


def retry_write(limiter: RateLimiter, operation: Callable[[], Any], attempts: int = 5) -> Any:
    for attempt in range(attempts):
        limiter.acquire()
        try:
            return operation()
        except Exception as exc:
            # The SDK wraps exhausted ABORTED attempts in ValueError.
            cause = exc.__cause__
            if not isinstance(exc, RETRYABLE) and not isinstance(cause, RETRYABLE):
                raise
            if attempt + 1 == attempts:
                raise
            time.sleep(min(8.0, 0.25 * 2**attempt) + random.uniform(0, 0.2))
    raise RuntimeError('unreachable')


def evaluate(runtime: Runtime, log: RunLog, job_id: str, *, limiter: RateLimiter) -> dict[str, Any]:
    record: dict[str, Any] = {
        'decision_id': uuid.uuid4().hex,
        'job_id': job_id,
        'timestamp': utc_now(),
        'class': None,
        'rule': None,
        'before': log.seal({}),
        'after': log.seal({}),
        'apply': log.config['apply'],
    }
    audit_written = False
    try:
        job_snapshot = runtime.client.collection(JOBS).document(job_id).get()
        job = job_snapshot.to_dict() or {}
        if not valid_binding(job):
            reason = 'invalid_job_binding'
        else:
            record['id_hash'] = safe_id(job['uid'], job['conversation_id'])
            ref = runtime.client.document(f"users/{job['uid']}/conversations/{job['conversation_id']}")
            snapshot = ref.get()
            row = snapshot.to_dict() if snapshot.exists else None
            if row is not None:
                record.update({'source': summary_source(row), 'audio_duration_bucket': audio_duration_bucket(row)})
            reason = eligibility(row, job_id, job)
            if reason is None:
                assert row is not None
                cls, rule, updates = classify(runtime, row, job, ref)
                record.update({'class': cls, 'rule': rule})
                if cls == 'K' and not log.config['include_kept_titles']:
                    reason = 'kept_titles_disabled'
                else:
                    before = {field: get_field(row, field) for field in updates}
                    after = {field: {'present': True, 'value': value} for field, value in updates.items()}
                    record.update(
                        {
                            'before': log.seal(before),
                            'after': log.seal(after),
                            'before_digest': digest(row),
                            'after_digest': digest(patched(row, after)),
                        }
                    )
                    # Durable intent BEFORE the transaction can commit.
                    log.append('audit.jsonl', record)
                    audit_written = True
                    if log.config['apply']:
                        write_result = retry_write(
                            limiter,
                            lambda: write_cas(
                                runtime,
                                job_id,
                                job,
                                row,
                                updates,
                                getattr(snapshot, 'update_time', None),
                                getattr(job_snapshot, 'update_time', None),
                            ),
                        )
                        outcome = write_result['outcome']
                        record['commit_revision'] = write_result['commit_revision']
                    else:
                        outcome = 'dry_run'
                    if outcome == 'written':
                        runtime.sync(job)
                    return dict(record, outcome=outcome)
    except CannotClassify as exc:
        reason = str(exc)
        record['rule'] = exc.rule
    except Exception as exc:
        # Exception bodies can carry plaintext/customer IDs. Only the type is safe.
        reason = 'error'
        record['error_type'] = type(exc).__name__
    record['skip_reason'] = reason
    if not audit_written:
        log.append('audit.jsonl', record)
    return dict(record, outcome=reason)


def discovery_pages(client: Any, cursor: str | None, page_size: int) -> Iterable[list[Any]]:
    while True:
        query = client.collection(JOBS)
        for field, value in JOB_FILTERS.items():
            query = query.where(filter=FieldFilter(field, '==', value))
        query = query.order_by('__name__').limit(page_size)
        if cursor:
            query = query.start_after({'__name__': client.collection(JOBS).document(cursor)})
        page = list(query.stream())
        if not page:
            return
        yield page
        cursor = page[-1].id
        if len(page) < page_size:
            return


def reconcile_pending(runtime: Runtime, log: RunLog, *, allow_projection: bool = False) -> None:
    for record in log.read('audit.jsonl'):
        if record['decision_id'] in log.results:
            continue
        outcome = record.get('skip_reason', 'dry_run')
        if record['apply'] and record.get('after_digest'):
            job = runtime.client.collection(JOBS).document(record['job_id']).get().to_dict() or {}
            if not valid_binding(job) or safe_id(job['uid'], job['conversation_id']) != record.get('id_hash'):
                outcome = 'interrupted_binding_missing'
            else:
                snapshot = runtime.client.document(f"users/{job['uid']}/conversations/{job['conversation_id']}").get()
                current = snapshot.to_dict() if snapshot.exists else None
                if current is not None and digest(current) == record['after_digest']:
                    outcome = 'written'
                    revision = getattr(snapshot, 'update_time', None)
                    record['commit_revision'] = revision.isoformat() if revision is not None else None
                    if allow_projection:
                        runtime.sync(job)
                elif current is not None and digest(current) == record['before_digest']:
                    outcome = 'error'  # not committed; retry on resume
                else:
                    outcome = 'interrupted_cas_changed'
        log.finish(record, outcome)


def run(
    runtime: Runtime,
    log: RunLog,
    *,
    workers: int = 8,
    max_writes_per_second: float = 20,
    limit: int | None = None,
    page_size: int = 200,
    error_threshold: float = 0.2,
    error_window: int = 50,
) -> dict[str, Any]:
    reconcile_pending(runtime, log, allow_projection=log.config['apply'])
    counts: Counter[str] = Counter()
    skips: Counter[str] = Counter()
    rules: Counter[str] = Counter()
    breakdown: dict[str, dict[str, dict[str, dict[str, int]]]] = {category: {} for category in BREAKDOWN_CATEGORIES}

    def count_breakdown(category: str, result: dict[str, Any]) -> None:
        by_rule = breakdown[category].setdefault(result['source'], {})
        buckets = by_rule.setdefault(result['rule'], dict.fromkeys(AUDIO_DURATION_BUCKETS, 0))
        buckets[result['audio_duration_bucket']] += 1

    samples: dict[str, list[str]] = {'R': [], 'K': []}
    recent: deque[bool] = deque(maxlen=error_window)
    limiter = RateLimiter(max_writes_per_second)
    processed = 0
    frozen = False
    stopped = False
    uids = set(log.config['uids'])
    ids = set(log.config['conversation_ids'])
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for page in discovery_pages(runtime.client, log.cursor, page_size):
            chosen = [
                s.id
                for s in page
                if s.id not in log.processed
                and (not uids or digest((s.to_dict() or {}).get('uid')) in uids)
                and (not ids or (s.to_dict() or {}).get('conversation_id') in ids)
            ]
            complete_page = True
            if limit is not None and len(chosen) > limit - processed:
                chosen = chosen[: limit - processed]
                complete_page = False
            # Submit at most workers at a time; no unbounded executor queue.
            for offset in range(0, len(chosen), workers):
                futures = [
                    pool.submit(evaluate, runtime, log, job_id, limiter=limiter)
                    for job_id in chosen[offset : offset + workers]
                ]
                for future in futures:
                    result = future.result()
                    log.finish(result, result['outcome'])
                    processed += 1
                    cls = result['class']
                    if cls:
                        counts[cls] += 1
                        rules[result['rule']] += 1
                        count_breakdown(cls, result)
                        if len(samples[cls]) < 20:
                            samples[cls].append(result['id_hash'])
                    if result['outcome'] not in ('written', 'dry_run'):
                        skips[result['outcome']] += 1
                        if result['outcome'] in ('discard_protected', 'empty_not_discardable'):
                            count_breakdown(result['outcome'], result)
                    else:
                        counts[result['outcome']] += 1
                    error = result['outcome'] == 'error'
                    recent.append(error)
                    frozen |= error
                if len(recent) == error_window and sum(recent) / error_window > error_threshold:
                    stopped = True
                    break
            if complete_page and not frozen and not stopped:
                log.checkpoint(page[-1].id)
            if stopped or (limit is not None and processed >= limit):
                break
    summary = {
        'apply': log.config['apply'],
        'processed': processed,
        'classes': dict(counts),
        'rules': dict(rules),
        'skip_reasons': dict(skips),
        'breakdown': breakdown,
        'samples': samples,
        'stopped_error_rate': stopped,
        'exit_code': 2 if frozen or stopped else 0,
    }
    log.save('summary.json', summary)
    return summary


def rollback(
    runtime: Runtime,
    source: RunLog,
    target: RunLog,
    *,
    qps: float = 20,
    workers: int = 8,
    limit: int | None = None,
    error_threshold: float = 0.2,
    error_window: int = 50,
) -> dict[str, Any]:
    limiter = RateLimiter(qps)
    counts: Counter[str] = Counter()
    recent: deque[bool] = deque(maxlen=error_window)
    reconcile_pending(runtime, source, allow_projection=target.config['apply'])
    reconcile_pending(runtime, target, allow_projection=target.config['apply'])
    candidates = [
        record
        for record in source.read('audit.jsonl')
        if source.results.get(record['decision_id'], {}).get('outcome') == 'written'
        and record['job_id'] not in target.processed
    ]
    if limit is not None:
        candidates = candidates[:limit]

    def undo(record: dict[str, Any]) -> dict[str, Any]:
        result = source.results[record['decision_id']]
        before, after = source.unseal(record['before']), source.unseal(record['after'])
        if not before or set(before) != set(after) or not set(before).issubset(ALLOWED_FIELDS):
            raise ValueError('invalid audit field allow-list')
        entry = dict(
            record,
            decision_id=uuid.uuid4().hex,
            timestamp=utc_now(),
            apply=target.config['apply'],
            before=target.seal(after),
            after=target.seal(before),
            before_digest=record['after_digest'],
            after_digest=record['before_digest'],
        )
        # Write-ahead rollback intent supports the same crash reconciliation.
        target.append('audit.jsonl', entry)
        try:
            job_ref = runtime.client.collection(JOBS).document(record['job_id'])
            job = job_ref.get().to_dict() or {}
            if not valid_binding(job) or safe_id(job['uid'], job['conversation_id']) != record.get('id_hash'):
                return dict(entry, outcome='binding_missing')
            ref = runtime.client.document(f"users/{job['uid']}/conversations/{job['conversation_id']}")

            def restore(transaction: Any) -> str:
                current_job = job_ref.get(transaction=transaction).to_dict() or {}
                snapshot = ref.get(transaction=transaction)
                current = snapshot.to_dict() if snapshot.exists else None
                if (
                    current_job != job
                    or current is None
                    or current.get('deleted')
                    or current.get('sync_relevance_user_kept')
                ):
                    return 'rollback_changed'
                revision = getattr(snapshot, 'update_time', None)
                if result.get('commit_revision') and (
                    revision is None or revision.isoformat() != result['commit_revision']
                ):
                    return 'rollback_changed'
                if digest(current) != record['after_digest'] or any(
                    get_field(current, k) != v for k, v in after.items()
                ):
                    return 'rollback_changed'
                if target.config['apply']:
                    transaction.update(
                        ref, {k: v['value'] if v['present'] else firestore.DELETE_FIELD for k, v in before.items()}
                    )
                    return 'written'
                return 'dry_run'

            def operation() -> str:
                if not target.config['apply']:
                    return restore(None)
                transaction = runtime.client.transaction(max_attempts=1)
                outcome = firestore.transactional(restore)(transaction)
                receipts = getattr(transaction, '_write_results', [])
                entry['commit_revision'] = receipts[-1].update_time.isoformat() if receipts else None
                return outcome

            outcome = retry_write(limiter, operation) if target.config['apply'] else operation()
            if outcome == 'written':
                runtime.sync(job)
            return dict(entry, outcome=outcome)
        except Exception as exc:
            return dict(entry, outcome='error', error_type=type(exc).__name__)

    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for offset in range(0, len(candidates), workers):
            futures = [pool.submit(undo, record) for record in candidates[offset : offset + workers]]
            for future in futures:
                result = future.result()
                target.finish(result, result['outcome'])
                counts[result['outcome']] += 1
                recent.append(result['outcome'] == 'error')
            if len(recent) == error_window and sum(recent) / error_window > error_threshold:
                stopped = True
                break
    summary = {
        'rollback': True,
        'apply': target.config['apply'],
        'outcomes': dict(counts),
        'stopped_error_rate': stopped,
        'exit_code': 2 if counts['error'] or stopped else 0,
    }
    target.save('summary.json', summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--include-kept-titles', action='store_true')
    parser.add_argument('--uid', action='append', default=[])
    parser.add_argument('--conversation-id-file', type=Path)
    directories = parser.add_mutually_exclusive_group(required=True)
    directories.add_argument('--run-dir', type=Path)
    directories.add_argument('--resume', type=Path)
    parser.add_argument('--rollback', type=Path, metavar='AUDIT_JSONL')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--max-writes-per-second', type=float, default=20)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--page-size', type=int, default=200)
    parser.add_argument('--error-threshold', type=float, default=0.2)
    parser.add_argument('--error-window', type=int, default=50)
    args = parser.parse_args()
    if (
        args.workers < 1
        or args.max_writes_per_second <= 0
        or args.page_size < 1
        or args.error_window < 1
        or not 0 <= args.error_threshold < 1
        or (args.limit is not None and args.limit < 1)
    ):
        parser.error('bounds must be positive; error-threshold must be in [0, 1)')
    ids = (
        sorted({s.strip() for s in args.conversation_id_file.read_text().splitlines() if s.strip()})
        if args.conversation_id_file
        else []
    )
    config = {
        'apply': args.apply,
        'include_kept_titles': args.include_kept_titles,
        'uids': sorted({digest(uid) for uid in args.uid}),
        'conversation_ids': ids,
        'rollback': str(args.rollback) if args.rollback else None,
    }
    path = args.resume or args.run_dir
    log = RunLog(path, config, resume=bool(args.resume))
    install_private_log_filters()
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(name)s %(message)s')
    lock_file = (path / 'run.lock').open('a')
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    runtime = Runtime(importlib.import_module('database._client').get_firestore_client())
    if args.rollback:
        if args.rollback.name != 'audit.jsonl' or not args.rollback.is_absolute():
            parser.error('rollback requires an absolute audit.jsonl path')
        source_path = args.rollback.parent
        source_lock = (source_path / 'run.lock').open('a')
        fcntl.flock(source_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        source_config = json.loads((source_path / 'config.json').read_text())
        source = RunLog(source_path, source_config, resume=True)
        summary = rollback(
            runtime,
            source,
            log,
            qps=args.max_writes_per_second,
            workers=args.workers,
            limit=args.limit,
            error_threshold=args.error_threshold,
            error_window=args.error_window,
        )
        source_lock.close()
    else:
        summary = run(
            runtime,
            log,
            workers=args.workers,
            max_writes_per_second=args.max_writes_per_second,
            limit=args.limit,
            page_size=args.page_size,
            error_threshold=args.error_threshold,
            error_window=args.error_window,
        )
    print(json.dumps(summary, sort_keys=True))
    lock_file.close()
    return summary['exit_code']


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({'fatal_error_type': type(error).__name__}), file=sys.stderr)
        sys.exit(2)
