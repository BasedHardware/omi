"""Observation only: bounded generation summaries, no scheduling or identity authority."""

import asyncio
import logging
import time
from collections import deque
from contextvars import ContextVar
from functools import wraps
from typing import Any

import config.owner_recognition_diagnostics as contract
from utils.observability.owner_identity_retry import resolver_trace

logger = logging.getLogger(__name__)
_UNBOUND = object()
_LIVE: ContextVar[Any] = ContextVar('owner_recognition_live_diagnostics', default=_UNBOUND)


def _live_row(default: "LiveGeneration | None" = None) -> "LiveGeneration | None":
    row = _LIVE.get()
    return default if row is _UNBOUND else row


_RESOLVER: ContextVar[dict[str, Any] | None] = ContextVar('owner_recognition_resolver_diagnostics', default=None)


class LiveGeneration:
    def __init__(self, **ids):
        self.data: dict[str, Any] = dict(ids, sequence=0, reasons={}, scopes=[])
        self.logged = set()
        self.closed = False

    def add(self, key, amount=1):
        if not self.closed:
            self.data[key] = self.data.get(key, 0) + amount
            self.data['sequence'] += 1

    def observe(self, reason, scope=''):
        if self.closed:
            return
        reason = reason if reason in contract.REASONS else 'other'
        reasons = self.data['reasons']
        reasons[reason] = min(reasons.get(reason, 0) + 1, contract.MAX_COUNT)
        self.data['reason'] = reason
        if reason in contract.COUNTS:
            self.add(reason)
        self.data['sequence'] += 1
        scope = contract.identifier(scope)
        if scope and scope not in self.data['scopes'] and len(self.data['scopes']) < contract.MAX_SCOPES:
            self.data['scopes'].append(scope)
        self.data['scope'] = scope or self.data.get('scope', '')
        # Reuse #21181's first-block log. No second budget log/cap counter here.
        if reason != 'embedding_budget' and reason not in self.logged:
            self.logged.add(reason)
            log_summary('live_refusal', self.data)

    def stop(self, reason, pending_queue, pending_tasks):
        if not self.closed:
            self.data.update(stop=reason, pending_queue=pending_queue, pending_tasks=pending_tasks)
            self.data['sequence'] += 1
            self.closed = True
            log_summary('live_stop', self.data)


class LiveDiagnostics:
    def __init__(self, host):
        self.host = host
        self.generations = deque(maxlen=contract.MAX_LIVE_GENERATIONS)
        self.current: LiveGeneration | None = None

    def begin(self, conversation, generation):
        self.current = LiveGeneration(
            uid=getattr(getattr(self.host, 'request', None), 'uid', ''),
            conversation=conversation or '',
            generation=generation,
            socket=getattr(self.host, 'session_id', ''),
            recording=getattr(self.host, 'recording_session_id', ''),
        )
        self.generations.append(self.current)

    def observe(self, reason, scope=''):
        row = _live_row(self.current)
        if row is not None:
            row.observe(reason, scope)

    def budget(self, cap):
        row = _live_row(self.current)
        if row is not None and cap in ('voice', 'socket', 'both'):
            row.add(f'budget_{cap}')

    def profile(self, row, eligible, failed, available, failures):
        if row is not None and not row.closed:
            row.data.update(owner_profile_available=int(available), profile_failures=failures)
            row.observe('profile_ineligible' if not eligible else 'profile_failed' if failed else 'profile_loaded')

    def snapshot(self, conversation):
        return contract.normalize(
            {'live': [row.data for row in self.generations if row.data['conversation'] == conversation]}
        )

    def checkpoint(self, conversation, queue, tasks):
        row = self.current
        if row is not None and row.data['conversation'] == conversation and not row.closed:
            values = dict(stop='finalized', pending_queue=queue.qsize(), pending_tasks=len(tasks))
            if any(row.data.get(k) != v for k, v in values.items()):
                row.data.update(values)
                row.data['sequence'] += 1
            if 'finalized' not in row.logged:
                row.logged.add('finalized')
                log_summary('live_stop', row.data)
        return self.snapshot(conversation)

    def stop(self, reason, queue, tasks):
        if self.current is not None:
            self.current.stop(reason, queue.qsize(), len(tasks))


def log_summary(event, data):
    try:
        safe = contract.summary(data)
        logger.info(
            'event=owner_recognition_diagnostics kind=%s uid=%s conversation=%s socket=%s scope=%s summary=%s',
            event,
            safe.get('uid', ''),
            safe.get('conversation', ''),
            safe.get('socket', ''),
            safe.get('scope', ''),
            safe,
        )
    except Exception:
        pass  # A diagnostic sink must never change matching/processing.


def observe_match(fn):
    @wraps(fn)
    async def observed(self, speaker_id, segment):
        row = self.diagnostics.current
        conversation = segment.get('conversation_id')
        generation = segment.get('_matcher_generation')
        if (
            row is None
            or (conversation and row.data['conversation'] != conversation)
            or (generation is not None and row.data['generation'] != generation)
        ):
            row = next(
                (
                    r
                    for r in reversed(self.diagnostics.generations)
                    if (not conversation or r.data['conversation'] == conversation)
                    and (generation is None or r.data['generation'] == generation)
                ),
                None,
            )
        token = _LIVE.set(row)
        try:
            if row is not None and not row.closed:
                row.data['scope'] = contract.identifier(segment.get('speaker_id_scope', ''))
            return await fn(self, speaker_id, segment)
        except asyncio.CancelledError:
            self.diagnostics.observe('cancelled')
            raise
        finally:
            _LIVE.reset(token)

    return observed


def observe_query(fn):
    @wraps(fn)
    async def observed(self, pcm):
        row = _live_row()
        if row is not None:
            row.add('attempted')
        try:
            result = await fn(self, pcm)
        except BaseException:
            if row is not None:
                row.add('failed')
                row.observe('extraction_failed')
            raise
        if row is not None:
            row.add('successful')
            row.add('pcm_seconds', len(pcm) / (2 * self.host.request.sample_rate))
        return result

    return observed


def live_comparison(distances, evidence_seconds):
    row = _live_row()
    if row is not None:
        row.add('comparisons')
        if 'user' in distances:
            row.add('owner_comparisons')
        if not row.closed:
            row.data['evidence_seconds'] = evidence_seconds


def resolver_reason(reason):
    row = _RESOLVER.get()
    if row is not None:
        row['reason'] = reason if reason in contract.REASONS else 'other'


def resolver_counts(**counts):
    row = _RESOLVER.get()
    if row is not None:
        row.update(contract.summary(counts))


def observe_resolver(fn):
    @wraps(fn)
    def observed(uid, conversation, **kwargs):
        trace = resolver_trace()
        row: dict[str, Any] = dict(
            uid=uid, conversation=getattr(conversation, 'id', ''), pass_=trace.pass_name if trace else 'first'
        )
        row['pass'] = row.pop('pass_')
        row['reason'] = 'empty_transcript'
        try:
            segments = getattr(conversation, 'transcript_segments', None) or []
            row['segments'] = len(segments)
            row['scopes'] = []
            for segment in segments:
                scope = contract.identifier(getattr(segment, 'speaker_id_scope', ''))
                if scope and scope not in row['scopes']:
                    row['scopes'].append(scope)
                    if len(row['scopes']) == contract.MAX_SCOPES:
                        break
            row['scope'] = row['scopes'][0] if row['scopes'] else ''
            prior = getattr(conversation, 'owner_recognition_diagnostics', None) or {}
            live = contract.normalize(prior).get('live', [])
            row['socket'] = live[-1].get('socket', '') if live else ''
        except Exception:
            pass  # Even malformed optional metadata cannot block the resolver.
        began = time.monotonic()
        token = _RESOLVER.set(row)
        try:
            return fn(uid, conversation, **kwargs)
        finally:
            try:
                row['elapsed_seconds'] = time.monotonic() - began
                resolution = getattr(conversation, 'speaker_resolution', None)
                row['status'] = getattr(resolution, 'status', 'absent')
                row['scores_present'] = bool(getattr(conversation, 'speaker_match_scores', None))
                log_summary('resolver_exit', row)
                if row['pass'] == 'first' and hasattr(conversation, 'owner_recognition_diagnostics'):
                    conversation.owner_recognition_diagnostics = contract.merge(
                        conversation.owner_recognition_diagnostics, {'first_resolver': row}
                    )
            except Exception:
                pass  # Optional diagnostics cannot alter the function's result or exception.
            finally:
                _RESOLVER.reset(token)

    return observed
