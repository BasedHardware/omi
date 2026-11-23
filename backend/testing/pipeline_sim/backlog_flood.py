"""Backlog-flood acceptance scenario for the fresh-first capture pipeline.

The flood is an initial-condition model of units whose transcription already
finished: admission is real, while its durable ``result_ready`` rows and result
artifacts are installed directly without a synthetic paid call. Fresh arrivals
still use the real provider stage, merge, serving and payer models. Projection
models the real OwnerDrains scheduler (eight owners, 15-second first turns or a
single FIFO queue, and 120-second backlog turns) over the durable result chain.
"""

from __future__ import annotations

import asyncio
import bisect
from collections import deque
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from testing.pipeline_sim.scorer import percentile, score
from testing.pipeline_sim.sim import SimConfig, Simulation, UploadRecord
from testing.pipeline_sim.stt import SPEECH, synthetic_words
from testing.pipeline_sim.workload import NORMAL, SegmentSpec, UploadSpec, content_id_for
from utils.batch_pipeline.contracts import WorkResult


class OwnerDrainProjection:
    """MODEL of ``projection_drain.OwnerDrains`` over the simulator's result rows.

    Discovery combines the oldest pending page with recent commits. Scheduling
    uses production's eight parallel owners and fair queues; one simulated row
    has the same executor cost as the ordinary projection model. Productive
    turns continue at the FIFO tail, and the predecessor chain is never cut.
    """

    MAX_OWNER_DRAINS = 8
    BACKLOG_TURN_SECONDS = 120.0
    STEP_SECONDS = 15.0
    BACKLOG_OWED_TURNS = 4

    def __init__(self, simulation: Simulation, first_turn_seconds: int):
        self.simulation = simulation
        self.first_turn_seconds = float(first_turn_seconds)
        self.queue: deque[str] = deque()
        self.backlog: deque[str] = deque()
        self.backlog_running: set[str] = set()
        self.yielding: set[str] = set()
        self.tasks: dict[str, asyncio.Task] = {}
        self.again: set[str] = set()
        self.continuations: set[str] = set()
        self.new_since_backlog = 0
        self.chains: dict[str, list[str]] = {}
        simulation.store.observers.append(self._result_written)

    def _result_written(self, address, previous, value) -> None:
        table, segment_id = address
        if table == 'results' and not previous:
            owner = value['owner_id']
            chain = self.chains.setdefault(owner, [])
            position = value['log_sequence']
            bisect.insort(
                chain,
                segment_id,
                key=lambda candidate: self.simulation.store.rows[('results', candidate)].get('log_sequence', position),
            )

    @property
    def classes(self) -> bool:
        return self.first_turn_seconds > 0

    def _pending_entries(self) -> list[tuple[float, str, dict]]:
        return sorted(
            (row['committed_at'], segment_id, row)
            for (table, segment_id), row in self.simulation.store.rows.items()
            if table == 'results' and row.get('projection_state') == 'pending'
        )

    def sweep(self) -> None:
        """Model the 100-row assignment page plus its recent-discovery half."""
        pending = self._pending_entries()
        recent_cutoff = self.simulation.clock.now - 120.0
        oldest = pending[:50]
        # Keep this quota separate: production reserves half the page for recent commits even
        # when thousands of older rows would otherwise fill the whole discovery page.
        recent = [entry for entry in pending if entry[0] >= recent_cutoff][-50:]
        self.request({entry[2]['owner_id'] for entry in [*oldest, *recent]})

    def request(self, owners) -> None:
        for owner in sorted(owners):
            if owner in self.tasks:
                self.again.add(owner)
            elif owner not in self.queue and owner not in self.backlog:
                self.queue.append(owner)
        self.launch()

    def next_owner(self) -> str | None:
        owed = not self.backlog_running and self.new_since_backlog >= self.BACKLOG_OWED_TURNS * self.MAX_OWNER_DRAINS
        if self.backlog and (not self.queue or owed):
            owner = self.backlog.popleft()
            self.backlog_running.add(owner)
            self.new_since_backlog = 0
            return owner
        if self.queue:
            self.new_since_backlog += 1
            return self.queue.popleft()
        return None

    def launch(self) -> None:
        while len(self.tasks) < self.MAX_OWNER_DRAINS:
            owner = self.next_owner()
            if owner is None:
                return
            continuation = owner in self.continuations
            self.continuations.discard(owner)
            turn = self.first_turn_seconds if self.classes and not continuation else self.BACKLOG_TURN_SECONDS
            unit = self.simulation.revision.spawn('projection-owner-drain', self.run(owner, turn))
            self.tasks[owner] = unit.task
            unit.task.add_done_callback(lambda done, owner=owner: self.finished(owner, done))

    def should_yield(self, owner: str) -> bool:
        if owner not in self.backlog_running or owner in self.yielding:
            return False
        waiting = len(self.queue) - (self.MAX_OWNER_DRAINS - len(self.tasks)) - len(self.yielding)
        if waiting <= 0 or len(self.backlog_running) - len(self.yielding) <= 1:
            return False
        self.yielding.add(owner)
        return True

    def next_record(self, owner: str) -> UploadRecord | None:
        for segment_id in self.chains.get(owner, ()):
            if self.simulation.store.rows[('results', segment_id)].get('projection_state') != 'pending':
                continue
            record = self.simulation.by_segment.get(segment_id)
            if record is None or record.projected_at is not None:
                return None
            return record
        return None

    async def run(self, owner: str, turn_seconds: float) -> bool:
        deadline = self.simulation.clock.now + turn_seconds
        next_step = self.simulation.clock.now + self.STEP_SECONDS
        advanced = 0
        more = False
        try:
            while self.simulation.clock.now < deadline or advanced == 0:
                if advanced and self.simulation.clock.now >= deadline:
                    more = True
                    break
                record = self.next_record(owner)
                if record is None:
                    break
                record.projecting = True
                await self.simulation._project(record)
                advanced += 1
                if self.simulation.clock.now >= next_step:
                    next_step = self.simulation.clock.now + self.STEP_SECONDS
                    if self.should_yield(owner):
                        more = True
                        break
                if self.next_record(owner) is None:
                    break
                if self.simulation.clock.now >= deadline:
                    more = True
                    break
        except Exception as error:
            self.simulation.counters[f'projection_model_error_{type(error).__name__}'] += 1
            return False
        return more

    def finished(self, owner: str, task: asyncio.Task) -> None:
        self.tasks.pop(owner, None)
        self.backlog_running.discard(owner)
        self.yielding.discard(owner)
        more = not task.cancelled() and task.exception() is None and task.result() is True
        if more:
            self.continuations.add(owner)
            (self.backlog if self.classes else self.queue).append(owner)
        elif owner in self.again:
            self.queue.append(owner)
        self.again.discard(owner)
        self.launch()


class BacklogFloodSimulation(Simulation):
    """Install the steady capture workload and the at-time backlog inventory."""

    def __init__(self, config: SimConfig):
        super().__init__(config)
        self.spec = config.backlog_flood or {}
        self.workload.uploads = self._uploads()
        for upload in self.workload.uploads:
            for segment in upload.segments:
                segment_id = self._segment_id(upload, segment.index)
                self.truth[segment_id] = {
                    'kind': segment.kind,
                    'duration': segment.duration,
                    'owner': upload.owner,
                    'upload': upload,
                }

    def _uploads(self) -> list[UploadSpec]:
        spec = self.spec
        fresh_owners = int(spec['fresh_owners'])
        interval = float(spec['fresh_interval_seconds'])
        flooded_owners = int(spec['flooded_owners'])
        fresh_flooded = int(spec['fresh_flooded_owners'])
        uploads = []
        steady_only_owners = fresh_owners - fresh_flooded
        for owner_index in list(range(fresh_flooded)) + list(
            range(flooded_owners, flooded_owners + steady_only_owners)
        ):
            for number in range(int(spec['steady_uploads_per_owner'])):
                upload_id = f'fresh-{owner_index:03d}-{number:03d}'
                uploads.append(
                    UploadSpec(
                        upload_id,
                        f'sim-owner-{owner_index:04d}',
                        NORMAL,
                        60.0 + number * interval,
                        recording_age=60.0 + (owner_index * 17 + number * 29) % 181,
                        content_id=content_id_for(upload_id),
                        segments=(SegmentSpec(0, 30.0, SPEECH),),
                    )
                )
        if spec['flood']:
            target_rows = int(spec['rows_per_flooded_owner']) * flooded_owners
            gpu_owners = min(6, max(1, flooded_owners - 1))
            gpu_rows = max(1, int(spec['rows_per_flooded_owner']) // 4)
            provider_owners = flooded_owners - gpu_owners
            provider_rows, extra_rows = divmod(target_rows - gpu_owners * gpu_rows, provider_owners)
            for owner_index in range(flooded_owners):
                rows = gpu_rows if owner_index < gpu_owners else provider_rows + (owner_index - gpu_owners < extra_rows)
                for number in range(rows):
                    upload_id = f'flood-{owner_index:03d}-{number:04d}'
                    uploads.append(
                        UploadSpec(
                            upload_id,
                            f'sim-owner-{owner_index:04d}',
                            NORMAL,
                            float(spec['flood_at']),
                            # Capture order is oldest to newest within each owner.
                            recording_age=86400.0 + (rows - number) * 60.0,
                            content_id=content_id_for(upload_id),
                            segments=(SegmentSpec(0, 30.0, SPEECH),),
                            lane='backfill',
                        )
                    )
        return sorted(uploads, key=lambda upload: (upload.at, upload.upload_id))

    async def _arrivals(self) -> None:
        for upload in self.workload.uploads:
            delay = max(0.0, upload.at - self.clock.elapsed())
            if delay > 0:
                await asyncio.sleep(delay)
            record = UploadRecord(upload)
            self.records.append(record)
            if upload.upload_id.startswith('flood-'):
                owner_index = int(upload.upload_id.split('-')[1])
                # Provider admission leaves no GPU ready-queue link. The stored route below then
                # selects the settled route being modeled; an initial GPU result must never re-run.
                super()._accept_batch(record, provider=True, deliver=False)
                assert record.status == 'admitted'
                gpu_owners = min(6, max(1, int(self.spec['flooded_owners']) - 1))
                self._seed_result_ready(record, provider=owner_index >= gpu_owners)
            else:
                super()._accept_batch(record)

    def _seed_result_ready(self, record: UploadRecord, *, provider: bool) -> None:
        """Install the post-transcription state, not a new ordering or writer."""
        for segment_id in record.segment_ids:
            item = SimpleNamespace(segment_id=segment_id)
            duration = self.truth[segment_id]['duration']
            result_uri = self.artifacts.persist_worker(
                item,
                {
                    'audio_seconds': duration,
                    'speech_seconds': duration,
                    'speech_spans': [{'start': 0.0, 'end': duration}],
                    'words': synthetic_words(duration),
                    'diarization': {'turns': []},
                    'words_provider': 'preseeded',
                    'language': self.config.language,
                },
            )
            job = self.store.rows[('jobs', segment_id)]
            changes = {
                'state': 'result_ready',
                'result': WorkResult(segment_id, result_uri, 'success').to_dict(),
                'ready_at': self.clock.now,
                'fresh_capture': False,
            }
            if provider:
                changes['provider_intent'] = {
                    'service': 'modulate',
                    'settled_at': self.clock.now,
                    'privacy_generation': job.get('privacy_generation'),
                }
            else:
                changes['stt_route'] = {
                    'stt_route': 'parakeet',
                    'provider_reason': 'none',
                    'provider_service': 'none',
                    'language': self.config.language,
                }
                changes['policy'] = {
                    **job['policy'],
                    'stt_route': 'parakeet',
                    'provider_reason': 'none',
                    'provider_service': 'none',
                }
                changes['requires_compute_admission'] = True
            self.store.mutate('jobs', segment_id, lambda row, changes=changes: row.update(changes))

    async def _provider_delivery(self, segment_id: str) -> None:
        """ProviderSttConsumer plus production's owner-local coalesced merge wake."""
        job = self.store.get('jobs', segment_id)
        if job.get('state') == 'provider_pending':
            await self.modulate.occupy(job['duration_seconds'])
        unit = self.provider_stage.run(segment_id)
        self.counters[f'provider_stt_{unit.outcome}'] += 1
        if unit.outcome in {'deferred', 'retry'}:
            delay = max(self.config.task_hop_seconds, (unit.available_at or 0.0) - self.clock.now)
            loop = asyncio.get_running_loop()
            loop.call_later(delay, lambda: loop.create_task(self._provider_delivery(segment_id)))
        elif self.serving is not None:
            self.serving.drain_owner(job['owner_id'])
            self.owner_projection.request([job['owner_id']])

    def _recovery_candidates(self, client, namespace, owner_id, limit=10, *, after_id=None):
        # The all-speech fixture has no recovery workload. Avoid scanning the large durable flood
        # on every maintenance tick; an unexpected quarantine still fails fresh/backlog completion.
        return []

    def _observe_fresh_guard(self) -> None:
        """Peak of the real closed 10–20 minute commit-window guard (sampled each loop minute)."""
        now = self.clock.now
        total = pending = 0
        for (table, _), row in self.store.rows.items():
            if (
                table == 'results'
                and row.get('fresh_capture') is True
                and now - 1200.0 <= row['committed_at'] <= now - 600.0
            ):
                total += 1
                pending += row.get('projection_state') == 'pending'
        prior_total = self.counters['fresh_guard_peak_denominator']
        prior_pending = self.counters['fresh_guard_peak_numerator']
        if total and (not prior_total or pending * prior_total > prior_pending * total):
            self.counters['fresh_guard_peak_numerator'] = pending
            self.counters['fresh_guard_peak_denominator'] = total
            self.counters['fresh_guard_peak_elapsed_ms'] = round(self.clock.elapsed() * 1000)

    def _drained(self) -> bool:
        self._observe_fresh_guard()
        if self.spec['release'] != 'held':
            return super()._drained()
        if len(self.records) != len(self.workload.uploads):
            return False
        if self.clock.elapsed() < max(upload.at for upload in self.workload.uploads):
            return False
        # Held provider inventory is intentionally permanent. The acceptance run ends once every
        # fresh obligation and its first summary has settled, rather than idling to the horizon.
        return all(
            record.projected_at is not None
            and (record.summary_pending_at is None or record.summary_completed_at is not None)
            for record in self.records
            if record.status == 'admitted' and not record.excluded and record.spec.upload_id.startswith('fresh-')
        )

    async def _main(self) -> float:
        self.owner_projection = OwnerDrainProjection(self, int(self.spec['first_turn_seconds']))
        self._projector_sweep = self.owner_projection.sweep
        return await super()._main()


def _rounded(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _capture_latency(record: UploadRecord) -> float:
    capture_end = record.accepted_at - record.spec.recording_age + sum(s.duration for s in record.spec.segments)
    return record.projected_at - capture_end


def fresh_baseline(result) -> dict[str, float | int | None]:
    """The serializable no-flood cohort shared by tests whose short chains are scheduler-identical."""
    fresh = [record for record in result.records if record.spec.upload_id.startswith('fresh-')]
    values = [_capture_latency(record) for record in fresh if record.projected_at is not None]
    return {
        'p50': _rounded(percentile(values, 0.5)),
        'p90': _rounded(percentile(values, 0.9)),
        'pending': sum(record.projected_at is None for record in fresh),
    }


def flood_metrics(result, baseline_result=None, *, baseline_summary=None) -> dict[str, Any]:
    spec = result.config.backlog_flood or {}
    fresh = [record for record in result.records if record.spec.upload_id.startswith('fresh-')]
    backlog = [record for record in result.records if record.spec.upload_id.startswith('flood-')]

    latencies = [_capture_latency(record) for record in fresh if record.projected_at is not None]
    p50, p90 = _rounded(percentile(latencies, 0.5)), _rounded(percentile(latencies, 0.9))
    baseline = baseline_summary or (fresh_baseline(baseline_result) if baseline_result is not None else None)

    projected_backlog = [record for record in backlog if record.projected_at is not None]
    last_projection = max((record.projected_at for record in projected_backlog), default=result.ended_at)
    flood_at = result.clock.start + float(spec['flood_at'])
    elapsed_minutes = max(60.0, last_projection - flood_at) / 60.0
    held = sum(
        result.store.rows.get(('jobs', segment_id), {}).get('state') == 'result_ready'
        for record in backlog
        for segment_id in record.segment_ids
    )
    routes: dict[str, int] = {}
    for record in backlog:
        for segment_id in record.segment_ids:
            job = result.store.rows.get(('jobs', segment_id), {})
            route = (job.get('stt_route') or {}).get('stt_route', 'unknown')
            routes[route] = routes.get(route, 0) + 1
    guard_num = result.counters.get('fresh_guard_peak_numerator', 0)
    guard_den = result.counters.get('fresh_guard_peak_denominator', 0)
    max_own_backlog_ahead = 0
    chain_valid = True
    for record in fresh:
        for segment_id in record.segment_ids:
            entry = result.store.rows.get(('results', segment_id))
            if not entry:
                continue
            committed_at = entry['committed_at']
            own_backlog_ahead = sum(
                (other.projected_at is None or other.projected_at >= committed_at)
                and any(
                    (other_entry := result.store.rows.get(('results', other_segment))) is not None
                    and other_entry['log_sequence'] < entry['log_sequence']
                    for other_segment in other.segment_ids
                )
                for other in backlog
                if other.spec.owner == record.spec.owner
            )
            max_own_backlog_ahead = max(max_own_backlog_ahead, own_backlog_ahead)

    by_owner: dict[str, list[tuple[int, str, str | None]]] = {}
    for (table, segment_id), entry in result.store.rows.items():
        if table == 'results':
            by_owner.setdefault(entry['owner_id'], []).append(
                (entry['log_sequence'], segment_id, entry.get('previous_segment_id'))
            )
    for rows in by_owner.values():
        rows.sort()
        chain_valid = chain_valid and rows[0][0] == 1
        for expected, row in enumerate(rows, start=1):
            chain_valid = (
                chain_valid and row[0] == expected and row[2] == (rows[expected - 2][1] if expected > 1 else None)
            )

    return {
        'release': spec['release'],
        'flood': bool(spec['flood']),
        'first_turn_seconds': spec['first_turn_seconds'],
        'fresh_owners': spec['fresh_owners'],
        'steady_hourly_volume': round(spec['fresh_owners'] * 3600.0 / spec['fresh_interval_seconds'], 3),
        'flooded_owners': spec['flooded_owners'] if spec['flood'] else 0,
        'fresh_flooded_owners': spec['fresh_flooded_owners'] if spec['flood'] else 0,
        'flooded_rows': len(backlog),
        'backlog_routes': dict(sorted(routes.items())),
        'flooded_to_steady_hourly_ratio': round(
            len(backlog) / (spec['fresh_owners'] * 3600.0 / spec['fresh_interval_seconds']), 3
        ),
        'fresh_capture_to_projection_p50_seconds': p50,
        'fresh_capture_to_projection_p90_seconds': p90,
        'fresh_baseline_p50_seconds': baseline['p50'] if baseline else p50,
        'fresh_baseline_p90_seconds': baseline['p90'] if baseline else p90,
        'fresh_p50_ratio': round(p50 / baseline['p50'], 3) if baseline and p50 and baseline['p50'] else 1.0,
        'fresh_p90_ratio': round(p90 / baseline['p90'], 3) if baseline and p90 and baseline['p90'] else 1.0,
        'fresh_pending': sum(record.projected_at is None for record in fresh),
        'backlog_rows_projected_per_minute': round(len(projected_backlog) / elapsed_minutes, 3),
        'backlog_projected': len(projected_backlog),
        'backlog_pending': len(backlog) - len(projected_backlog),
        'held_result_ready': held,
        'fresh_unprojected_10_to_20_minutes_share': round(guard_num / guard_den, 4) if guard_den else 0.0,
        'fresh_unprojected_10_to_20_minutes_numerator': guard_num,
        'fresh_unprojected_10_to_20_minutes_denominator': guard_den,
        'fresh_guard_peak_elapsed_seconds': result.counters.get('fresh_guard_peak_elapsed_ms', 0) / 1000,
        'max_own_backlog_rows_ahead_of_fresh': max_own_backlog_ahead,
        'owner_chain_valid': chain_valid,
    }


def run_backlog_flood(config: SimConfig, *, baseline_summary=None) -> dict[str, Any]:
    """Run one release arm against its same-seed no-flood baseline or its serializable summary."""
    release = (config.backlog_flood or {})['release']
    if release == 'gated':
        # Step 4 installs the commit gate here; do not label unmetered rollback as metered release.
        raise ValueError("release='gated' is reserved for the step-4 commit gate")
    if config.path == 'legacy':
        raise ValueError('the backlog flood scenario only models the batch path')
    result = BacklogFloodSimulation(config).run()
    sample = score(result)
    metrics = flood_metrics(result, baseline_summary=baseline_summary)
    if config.backlog_flood['flood'] and baseline_summary is None:
        baseline_spec = {**config.backlog_flood, 'flood': False}
        baseline_result = BacklogFloodSimulation(replace(config, backlog_flood=baseline_spec)).run()
        metrics = flood_metrics(result, baseline_result)
    sample['sim']['backlog_flood'] = metrics
    sample['sim']['fleet_gate_verdict'] = sample['verdict']
    failures = []
    if metrics['fresh_pending']:
        failures.append('fresh_incomplete')
    p50_ratio, p90_ratio = metrics['fresh_p50_ratio'], metrics['fresh_p90_ratio']
    if p50_ratio > 1.1 or p90_ratio > 1.1:
        failures.append('fresh_latency')
    if metrics['max_own_backlog_rows_ahead_of_fresh'] > config.backlog_flood['catch_up_depth']:
        failures.append('owner_backlog_depth')
    if not metrics['owner_chain_valid']:
        failures.append('owner_chain')
    if release == 'unmetered' and metrics['backlog_pending']:
        failures.append('backlog_incomplete')
    sample['verdict'] = 'GATE_PASS' if not failures else 'GATE_FAIL ' + '+'.join(failures)
    sample['verdict_code'] = 0 if not failures else 1
    return sample
