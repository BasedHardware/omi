"""Content-free clocks; committed note counts come from durable receipts."""

from functools import cache
from typing import TypedDict
from prometheus_client import Counter, Histogram


class Collectors(TypedDict):
    stage: Histogram
    notes: Histogram
    closed: Histogram
    open: Histogram
    rewrites: Histogram
    events: Counter


@cache
def collectors() -> Collectors:
    buckets = (1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 21600, 86400)
    return {
        'stage': Histogram(
            'omi_pipeline_stage_seconds', 'Server stage clocks', ['stage', 'attention'], buckets=buckets
        ),
        'notes': Histogram(
            'omi_pipeline_capture_to_notes_seconds',
            'Capture span end to first durable generated notes',
            ['attention', 'lane'],
            buckets=buckets,
        ),
        'closed': Histogram(
            'omi_pipeline_close_to_notes_seconds',
            'Close trigger to first durable notes; watched target clock',
            ['attention', 'lane'],
            buckets=buckets,
        ),
        'open': Histogram(
            'omi_pipeline_open_to_ready_seconds',
            'Open to existing text with truthful pending markers',
            ['trigger', 'initial_state'],
            buckets=buckets,
        ),
        'rewrites': Histogram(
            'omi_pipeline_notes_rewrites_per_conversation',
            'Durable automatic note versions minus first, at commit',
            ['reason'],
            buckets=(0, 1, 2, 3, 5, 10, 20),
        ),
        'events': Counter('omi_pipeline_attention_total', 'Pipeline decisions and missing clocks', ['outcome']),
    }


def event(outcome):
    allowed = {
        'seal_denied',
        'projection_pending',
        'fast',
        'patient_wait',
        'deadline',
        'shadow',
        'unknown_capture_clock',
        'unknown_attention',
        'dependency_unavailable',
        'notes_attempt',
        'stale_commit',
        'unchanged',
        'record_wake',
        'unknown_denominator',
    }
    collectors()['events'].labels(outcome if outcome in allowed else 'dependency_unavailable').inc()


def committed(receipt):
    if not receipt:
        return
    c = collectors()
    attention = receipt['attention']
    if receipt['first']:
        if receipt['capture_latency'] is None:
            event('unknown_capture_clock')
        else:
            c['notes'].labels(attention, receipt['lane']).observe(receipt['capture_latency'])
        if receipt['close_latency'] is not None:
            c['closed'].labels(attention, receipt['lane']).observe(receipt['close_latency'])
    c['rewrites'].labels(receipt['reason']).observe(receipt['rewrites'])


def open_ready(seconds, *, trigger, initial_state):
    if trigger not in {'app_open', 'api_read', 'mcp_read'}:
        raise ValueError('unknown promotion trigger')
    if initial_state not in {'warm_ready', 'transcript_only', 'untranscribed', 'unsealed', 'unknown'}:
        raise ValueError('unknown initial state')
    collectors()['open'].labels(trigger, initial_state).observe(seconds)


def stage(name, seconds, attention='unknown'):
    if name not in {
        'capture_to_seal',
        'speech_to_seal',
        'producer_finish_to_seal',
        'record_queue',
        'record_admission',
        'silence_configured',
        'conversation_gap',
        'notes_work',
        'user_finalize_wait',
    }:
        raise ValueError('unknown stage')
    if attention not in {'watched', 'unwatched', 'unknown'}:
        raise ValueError('unknown attention')
    if seconds is not None and seconds >= 0:
        collectors()['stage'].labels(name, attention).observe(seconds)
