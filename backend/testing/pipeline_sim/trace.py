"""Normalized, externally visible event trace of one simulated batch-pipeline run (characterization goldens).

The trace is built only from what a caller or operator could observe:

- durable store writes, captured through ``SimStore.observers`` (each committed
  row change) and ``SimStore.delete`` (purges), collapsed to per-segment state
  transitions;
- HTTP-visible outcomes: the upload intake status code and the
  ``/recover-quarantine`` task-handler response for every delivery;
- paid fallback calls per segment and the final job, result and content rows;
- conversation-visible results: projection, exclusion, word count and hash,
  speech seconds and first-summary state.

It is never built from internal function-call order. Nondeterminism and
irrelevant detail are normalized away: synthetic IDs are renamed by first
appearance in arrival order (``owner-1``, ``upload-1``, ``seg-1``, ``conv-1``),
lease and intent tokens, URIs, owner hashes and queue links are dropped,
absolute timestamps are dropped and transition times become coarse buckets
relative to the segment's admission, and every dict is key-sorted on dump.

``GOLDEN_CONFIGS`` are the small seeded runs pinned by
``tests/unit/test_pipeline_characterization.py``.
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import re
from dataclasses import replace
from typing import Any, Callable

from testing.pipeline_sim.sim import SimConfig, Simulation
from testing.pipeline_sim.stt import ExhaustionWindow, ModulateProfile, STTProfile
from testing.pipeline_sim.workload import WorkloadSpec

SCHEMA = 'pipeline_sim.trace/v1'

# Upper bucket edges (seconds after the segment's admission). They straddle the
# operational thresholds the fleet gate uses (5 min quarantine projection, 15 min obligations).
_BUCKETS = ((1, '<1s'), (5, '<5s'), (30, '<30s'), (60, '<1m'), (300, '<5m'), (900, '<15m'), (3600, '<1h'))

# Row fields that are tokens, pointers, hashes, URIs or duplicates of the row key.
_DROP_FIELDS = frozenset(
    (
        'audio_uri',
        'result_uri',
        'owner_key',
        'next',
        'previous',
        'shared_gpu_key',
        'projection_binding',
        'policy',  # metadata, not part of the pre-E1 external behavior trace
        'policy_source',
        'policy_parts',
        'segment_id',
        'segment_ids',
        'log_tail',
        'revision',
        'watermark',
    )
)
_HEX64 = re.compile(r'[0-9a-f]{64}')

# intake.accept_upload: 202 for an admitted or deduplicated (same content) upload, 409 when privacy-blocked.
_HTTP_STATUS = {'admitted': 202, 'deduplicated': 202, 'rejected_privacy': 409}


def _bucket(seconds: float) -> str:
    for edge, label in _BUCKETS:
        if seconds < edge:
            return label
    return '>=1h'


def _dropped(key: str) -> bool:
    return key in _DROP_FIELDS or 'token' in key or key.endswith('_at') or key.endswith('_until')


class _Aliases:
    """Synthetic ID -> stable alias, assigned by first appearance."""

    def __init__(self, *, include_policy=False):
        self.include_policy = include_policy
        self.names: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    def add(self, raw: str | None, kind: str) -> str | None:
        if raw is None:
            return None
        if raw not in self.names:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            self.names[raw] = f'{kind}-{self.counts[kind]}'
        return self.names[raw]

    def scrub(self, value: Any) -> Any:
        """Recursively drop volatile fields, rename known IDs and round floats."""
        if isinstance(value, dict):
            return {
                key: (item if key == 'policy_id' and self.include_policy else self.scrub(item))
                for key, item in value.items()
                if not _dropped(key) or self.include_policy and key in {'policy', 'policy_source', 'policy_parts'}
            }
        if isinstance(value, (list, tuple)):
            return [self.scrub(item) for item in value]
        if isinstance(value, float):
            return round(value, 3)
        if isinstance(value, str):
            if value in self.names:
                return self.names[value]
            return _HEX64.sub('<hex64>', value)
        return value


class _Recorder:
    """Store observer + task-handler wrapper. Records only durable and response-level facts."""

    def __init__(self, sim: Simulation):
        self.sim = sim
        self.admitted_at: dict[str, float] = {}
        self.transitions: dict[str, list] = {}
        self.result_transitions: dict[str, list] = {}
        self.responses: dict[str, list[str]] = {}
        sim.store.observers.append(self._observe)
        delete = sim.store.delete

        def recorded_delete(table: str, key: str) -> None:
            existed = (table, key) in sim.store.rows
            delete(table, key)
            if existed and table == 'jobs':
                self._append(self.transitions, key, ('purged',))
            elif existed and table == 'results':
                self._append(self.result_transitions, key, ('deleted',))

        sim.store.delete = recorded_delete  # instance attribute; purge() resolves it through self
        handler = sim._recover_handler

        async def recorded_handler(segment_id: str, task_id: str | None = None) -> str:
            try:
                outcome = await handler(segment_id, task_id)
            except asyncio.CancelledError:
                # Only the end of the run cancels a delivery (request-scoped work survives revision drain).
                self.responses.setdefault(segment_id, []).append('unfinished_at_end')
                raise
            self.responses.setdefault(segment_id, []).append(outcome)
            return outcome

        sim._recover_handler = recorded_handler

    def _append(self, log: dict, key: str, signature: tuple[str, ...]) -> None:
        now = self.sim.clock.now
        start = self.admitted_at.setdefault(key, now)
        entries = log.setdefault(key, [])
        if entries and entries[-1][1] == signature:
            return
        entries.append((_bucket(now - start), signature))

    def _observe(self, address: tuple[str, str], previous: dict, row: dict) -> None:
        table, key = address
        if table == 'jobs':
            signature = (
                row.get('state'),
                f"recovery:{row['recovery_state']}" if row.get('recovery_state') else None,
                f"client:{row['client_status']}" if row.get('client_status') else None,
            )
            self._append(self.transitions, key, tuple(part for part in signature if part))
        elif table == 'results':
            outcome = (row.get('result') or {}).get('outcome')
            state = 'erased' if row.get('erased') else row.get('projection_state', 'committed')
            self._append(self.result_transitions, key, (state, f'outcome:{outcome}'))


def _payload(sim: Simulation, result_row: dict | None) -> dict:
    """The committed result artifact (what projection reads); empty once the result is erased or deleted."""
    if not result_row or result_row.get('erased'):
        return {}
    return sim.artifacts.objects.get((result_row.get('result') or {}).get('result_uri'), {})


def _words(sim: Simulation, result_row: dict | None) -> list:
    if ((result_row or {}).get('result') or {}).get('outcome') != 'success':
        return []
    return list(_payload(sim, result_row).get('words') or [])


def _digest(words: list) -> int:
    """48-bit content digest, kept numeric so secret scanners do not read a hex string as a credential."""
    return int(hashlib.sha256(json.dumps(words, sort_keys=True).encode()).hexdigest()[:12], 16)


def _artifact(sim: Simulation, result_row: dict | None) -> dict | None:
    payload = _payload(sim, result_row)
    if not payload:
        return None
    words = list(payload.get('words') or [])
    summary = {key: payload.get(key) for key in ('words_provider', 'outcome', 'recognition_evidence', 'language')}
    summary.update(
        audio_seconds=payload.get('audio_seconds'),
        speech_seconds=payload.get('speech_seconds'),
        words=len(words),
        words_digest=_digest(words),
    )
    return {key: value for key, value in summary.items() if value is not None}


def trace(config: SimConfig, *, prepare: Callable[[Simulation], None] | None = None) -> dict[str, Any]:
    """Run ``config`` (batch path) and return its normalized trace. ``prepare`` may perturb the sim before it runs."""
    if config.path != 'batch':
        raise ValueError('characterization traces cover the batch state machine only')
    sim = Simulation(config)
    recorder = _Recorder(sim)
    if prepare is not None:
        prepare(sim)
    result = sim.run()
    store = result.store

    aliases = _Aliases(include_policy=config.trace_policy)
    by_upload = {record.spec.upload_id: record for record in result.records}
    for upload in result.workload.uploads:
        aliases.add(upload.owner, 'owner')
        aliases.add(upload.upload_id, 'upload')
        aliases.add('bp_' + (upload.duplicate_of or upload.upload_id), 'job')
        aliases.add(upload.content_id, 'content')
        aliases.add(sim._target_id(upload) if upload.target else None, 'conv')
        aliases.add(sim._target_id(upload) + '-merged' if upload.target == 'merged' else None, 'conv')
        for segment in upload.segments:
            aliases.add(sim._segment_id(upload, segment.index), 'seg')
    for upload in result.workload.uploads:  # chunk-identity conversations, in segment order
        for segment in upload.segments:
            job = store.rows.get(('jobs', sim._segment_id(upload, segment.index)))
            result_row = store.rows.get(('results', sim._segment_id(upload, segment.index)))
            for row in (job, result_row):
                if row and row.get('conversation_id'):
                    aliases.add(row['conversation_id'], 'conv')

    uploads = []
    for upload in result.workload.uploads:
        record = by_upload.get(upload.upload_id)
        status = record.status if record else 'not_arrived'
        entry: dict[str, Any] = {
            'upload': aliases.names[upload.upload_id],
            'owner': aliases.names[upload.owner],
            'duplicate_of': aliases.scrub(upload.duplicate_of),
            'target': upload.target,
            'lane': upload.lane,
            'intake': status,
            'http_status': _HTTP_STATUS.get(status),
        }
        if status == 'admitted':
            words = []
            for sid in record.segment_ids:
                words.extend(_words(sim, store.rows.get(('results', sid), {})))
            if record.summary_completed_at is not None:
                summary = 'completed'
            elif record.summary_pending_at is not None:
                summary = 'pending'
            else:
                summary = 'none'
            content = store.rows.get(('content', f'{upload.owner}/{upload.content_id}'), {})
            entry.update(
                job=aliases.names[record.job_id],
                segments=[aliases.names[sid] for sid in record.segment_ids],
                content_status=content.get('status'),
                conversation={
                    'projected': record.projected_at is not None,
                    'excluded': record.excluded,
                    'speech_seconds': round(record.speech_seconds, 3),
                    'words': len(words),
                    'words_digest': _digest(words),
                    'first_summary': summary,
                    'summary_dispatches': record.summary_dispatches,
                },
            )
        uploads.append(entry)

    segments: dict[str, Any] = {}
    for upload in result.workload.uploads:
        for segment in upload.segments:
            sid = sim._segment_id(upload, segment.index)
            alias = aliases.names[sid]
            if alias in segments:
                continue  # a duplicate upload re-uses the original's segments
            job = store.rows.get(('jobs', sid))
            result_row = store.rows.get(('results', sid))
            segments[alias] = {
                'owner': aliases.names[upload.owner],
                'content_kind': segment.kind,
                'duration_seconds': segment.duration,
                'job_transitions': _lines(recorder.transitions.get(sid, [])),
                'result_transitions': _lines(recorder.result_transitions.get(sid, [])),
                'recover_task_responses': recorder.responses.get(sid, []),
                'paid_calls': result.modulate.calls_by_segment.get(sid, 0),
                'final_job': aliases.scrub(job) if job is not None else None,
                'final_result': aliases.scrub(result_row) if result_row is not None else None,
                'result_artifact': aliases.scrub(_artifact(sim, result_row)),
            }

    output = {
        'schema': SCHEMA,
        'config': config.name,
        'seed': config.seed,
        'uploads': uploads,
        'segments': segments,
        'totals': {
            'paid_calls': result.modulate.calls,
            'paid_outcomes': dict(sorted(result.modulate.outcomes.items())),
            'counters': dict(sorted(result.counters.items())),
            'revision_drain': result.revision.report.counts(),
            'job_states': _count(row.get('state') for row in store.jobs()),
            'recovery_states': _count(row.get('recovery_state') for row in store.jobs() if row.get('recovery_state')),
        },
    }

    if any(
        record.first_summary_policy and not record.first_summary_policy.first_summary_enabled
        for record in result.records
    ):
        from testing.pipeline_sim.scorer import score

        # Expose policy-window grading only when an obligation is outside the
        # first-summary cohort. Historical (all-enabled) traces stay identical.
        sample = score(result)
        output['first_summary_policy'] = {
            'recorded_enabled': sorted(
                {
                    record.first_summary_policy.first_summary_enabled
                    for record in result.records
                    if record.first_summary_policy
                }
            ),
            'checked': sample['first_summary_checked_conversations'],
            'breaches': sample['first_summary_deadline_breaches'],
        }
    return output


def _lines(entries: list[tuple[str, tuple[str, ...]]]) -> list[str]:
    """``['<5s quarantined recovery:held', ...]``: one diff-friendly line per durable transition."""
    return [' '.join((bucket, *signature)) for bucket, signature in entries]


def _count(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=1, sort_keys=True) + '\n'


def changed_paths(expected: Any, actual: Any, path: str = '') -> list[str]:
    """JSON paths whose values differ (``segments.seg-3.paid_calls``), for a one-line summary."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        paths = []
        for key in sorted(set(expected) | set(actual), key=str):
            child = f'{path}.{key}' if path else str(key)
            if key not in expected or key not in actual:
                paths.append(child)
            else:
                paths.extend(changed_paths(expected[key], actual[key], child))
        return paths
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        paths = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            paths.extend(changed_paths(left, right, f'{path}[{index}]'))
        return paths
    return [] if expected == actual else [path or '<root>']


def describe_diff(expected_text: str, actual_text: str, *, label: str, max_lines: int = 120) -> str:
    """Changed JSON paths followed by a bounded unified diff of the dumped traces."""
    paths = changed_paths(json.loads(expected_text), json.loads(actual_text))
    lines = list(
        difflib.unified_diff(
            expected_text.splitlines(), actual_text.splitlines(), f'golden/{label}', f'actual/{label}', lineterm='', n=2
        )
    )
    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown.append(f'... {len(lines) - max_lines} more diff lines')
    head = f'{len(paths)} changed path(s): ' + ', '.join(paths[:12]) + (' ...' if len(paths) > 12 else '')
    return '\n'.join([head, *shown])


# ----------------------------------------------------------------------------- golden configurations

_SMALL = dict(owners=3, uploads_per_owner_per_hour=3.0, arrival_seconds=1200.0, silence_fraction=0.0)


def _config(name: str, *, seed: int = 7, workload: dict | None = None, **changes: Any) -> SimConfig:
    spec = WorkloadSpec(**{**_SMALL, 'near_silence_fraction': 0.0, **(workload or {})})
    changes.setdefault('stt', STTProfile(min_replicas=2, max_replicas=2, near_silence_empty_rate=0.0))
    return replace(SimConfig(name=name, seed=seed, horizon_seconds=2 * 3600.0), workload=spec, **changes)


GOLDEN_CONFIGS: dict[str, Callable[[], SimConfig]] = {
    # Speech only, healthy fleet: admitted -> ready -> leased -> committed -> projected.
    'healthy': lambda: _config('healthy'),
    # Explicit serving-revision split: only the integration owner chooses stage knobs.
    'role_policy': lambda: _config(
        'role_policy',
        trace_policy=True,
        workload={'owners': 1, 'arrival_seconds': 400.0, 'uploads_per_owner_per_hour': 18.0},
        stt=STTProfile(min_replicas=2, max_replicas=2, exhaustion=(ExhaustionWindow(0.0, 1500.0, 'error'),)),
        role_environments={
            'sync': {
                'K_SERVICE': 'sync',
                'BATCH_PIPELINE_RECOVERY_MODE': 'off',
                'BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED': 'false',
            },
            'integration': {
                'K_SERVICE': 'integration',
                'BATCH_PIPELINE_RECOVERY_MODE': 'on',
                'BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED': 'true',
            },
        },
        stage_roles={
            'admission': 'sync',
            'recovery': 'integration',
            'projection': 'integration',
            'first_summary': 'integration',
        },
    ),
    # 10-18: creation at percent zero must not acquire a 120s obligation after a ramp.
    'policy_window': lambda: _config(
        'policy_window',
        flags={'FIRST_SUMMARY_DEADLINE_PERCENT': '0'},
        summary_seconds=300.0,
        summary_sigma=0.0,
    ),
    # Near-silence with empty first ASR: padded retry recovers some; the rest quarantine as empty_asr,
    # spend one paid call and either recover or settle as terminal empty (no_recoverable_speech).
    'empty_asr_padded_retry': lambda: _config(
        'empty_asr_padded_retry',
        workload={'near_silence_fraction': 0.7},
        stt=STTProfile(min_replicas=2, max_replicas=2, near_silence_empty_rate=0.6),
        modulate=ModulateProfile(near_silence_recover_rate=0.5),
    ),
    # Every first and padded ASR attempt is empty and the paid provider finds no speech: terminal empty.
    'empty_asr_terminal': lambda: _config(
        'empty_asr_terminal',
        workload={'near_silence_fraction': 1.0, 'owners': 2},
        stt=STTProfile(min_replicas=2, max_replicas=2, near_silence_empty_rate=1.0),
        modulate=ModulateProfile(near_silence_recover_rate=0.0),
    ),
    # C8 with legacy draining: a language Parakeet cannot serve is admitted to the provider-STT stage,
    # never leased by a GPU pump, pays exactly one vendor call per unit and merges in capture order.
    'provider_stt_ja': lambda: _config('provider_stt_ja', language='ja', legacy_sync='draining'),
    'provider_stt_unsupported': lambda: _config('provider_stt_unsupported', language='sw', legacy_sync='draining'),
    # BYOK routes like everyone (David, 10-19): Parakeet, no vendor spend; the admission policy
    # records provider_reason=byok so the keyless dispatch re-check never re-holds it.
    'provider_stt_byok': lambda: _config('provider_stt_byok', byok=True, legacy_sync='draining', trace_policy=True),
    # Provider errors for a window: retries exhaust attempts -> quarantine -> one paid recovery each.
    'provider_failure_quarantine': lambda: _config(
        'provider_failure_quarantine',
        stt=STTProfile(min_replicas=2, max_replicas=2, exhaustion=(ExhaustionWindow(0.0, 1500.0, 'error'),)),
    ),
    # One owner blocked before admission (409) and one fenced mid-flight while quarantines are pending.
    'privacy_fence_midflight': lambda: _config(
        'privacy_fence_midflight',
        seed=4,  # the mid-flight owner has captures quarantined on both sides of the fence
        workload={
            'owners': 4,
            'uploads_per_owner_per_hour': 6.0,
            'arrival_seconds': 900.0,
            'privacy_blocked_owners': 1,
            'privacy_midflight_owners': 1,
            'privacy_midflight_at': 680.0,
        },
        # Empty ASR quarantines everything before the fence; one slow paid slot keeps recoveries queued across it.
        stt=STTProfile(min_replicas=2, max_replicas=2, exhaustion=(ExhaustionWindow(0.0, 680.0, 'empty'),)),
        modulate=ModulateProfile(concurrency=1, base_latency_seconds=60.0),
    ),
    # Finalize targets merged (redirect) or deleted (tombstone + purge) while in flight.
    'deleted_merged_targets': lambda: _config(
        'deleted_merged_targets',
        workload={
            'owners': 4,
            'uploads_per_owner_per_hour': 6.0,
            'merged_target_fraction': 0.35,
            'deleted_target_fraction': 0.35,
        },
    ),
    # Same content uploaded twice, worker complete/fail RPCs and recovery tasks delivered twice.
    'duplicate_delivery': lambda: _config(
        'duplicate_delivery',
        workload={'duplicate_upload_fraction': 0.5, 'near_silence_fraction': 0.4},
        stt=STTProfile(min_replicas=2, max_replicas=2, near_silence_empty_rate=1.0),
        recovery_duplicate_delivery_rate=1.0,
        worker_rpc_duplicate_rate=1.0,
    ),
    # CPU revision replaced mid-run (GPU pumps SIGTERMed and restarted); first summaries run in background.
    'revision_replacement': lambda: _config(
        'revision_replacement',
        workload={'owners': 4, 'near_silence_fraction': 0.2},
        stt=STTProfile(min_replicas=2, max_replicas=2, near_silence_empty_rate=1.0),
        summary_dispatch='background',
        summary_seconds=300.0,
        revision_replacement_at=500.0,  # while a background first summary is still running
    ),
}


def golden_trace(name: str, **kwargs: Any) -> dict[str, Any]:
    return trace(GOLDEN_CONFIGS[name](), **kwargs)
