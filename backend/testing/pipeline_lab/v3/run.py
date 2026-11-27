"""Compose a v3 day replay: environment, start state, admission, the event loop, export, day stages.

Same environment as the classic chain (``chain/run.py``): the persistent emulator stack, the
in-process vector index, capture-only sinks, the executor barrier and the virtual clock. On top:

- the simulated clock by default (``clock='sim'``, ``stack/clock.py``): product code sees only the
  replay's instants, and its monotonic and loop clocks follow them across events, so the same
  inputs give the same day. Overlay ``model_config.v3.clock: "tick"`` restores the ticking clock
  (each pass stamped at its instant plus real latency);

- the loopback Cloud Tasks queue (``v3/tasks.py``), so the product's reconcile wakes run in
  process at their scheduled virtual time;
- the admission evidence and attribution hooks (``v3/product.py``);
- a placeholder reconcile base URL (``CONVERSATIONS_V3_TASKS_URL``), which production derives
  from its task handler URL and which the lab never contacts (the queue is loopback).

Outputs in the run directory: ``conversations/<v3 id>.json`` (contract rows with
``recordings`` and ``v3``), ``chain.json`` (per-conversation status, as the chain stages read),
``v3_driver.json`` (arrival plan and every event), ``v3_tasks.jsonl`` (every named task),
``v3_recordings.json`` (where each recording's speech went), and the day files from ``day/``.
"""

from __future__ import annotations

from contextlib import ExitStack
import os
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from testing.pipeline_lab.chain.barrier import ExecutorBarrier
from testing.pipeline_lab.chain.driver import ProductChainStore, ProductFinalizer, llm_call_ids_by_conversation
from testing.pipeline_lab.chain.run import PRODUCT_MODULES, _record_processing_failures
from testing.pipeline_lab.sinks.capture import CaptureSinks
from testing.pipeline_lab.stack.clock import LabClock, installed_clock
from testing.pipeline_lab.stack.config import LabStackConfig
from testing.pipeline_lab.stack.env import lab_environment
from testing.pipeline_lab.stack.io import append_jsonl, parse_time, write_json
from testing.pipeline_lab.stack.overlay import Overlay
from testing.pipeline_lab.v3.driver import V3Driver, default_horizon
from testing.pipeline_lab.v3.export import home_visible, normalize_v3_conversation, pair_by_recordings
from testing.pipeline_lab.v3.feed import DEFAULT_LAG, plan_arrivals, word_count
from testing.pipeline_lab.v3.product import (
    V3_MODULES,
    ProductV3Ops,
    admit,
    clear_admission,
    install_attribution,
    install_emulator_size_errors,
    install_planner_trace,
    TRACE_ENV,
    read_v3_rows,
)
from testing.pipeline_lab.v3.tasks import LoopbackTasks

TASKS_URL_ENV = 'CONVERSATIONS_V3_TASKS_URL'
LOOPBACK_TASKS_URL = 'http://pipeline-lab-loopback.invalid'


@dataclass
class V3RunSpec:
    run_dir: Path
    day_start: datetime
    day_end: datetime
    recordings: Sequence[Mapping[str, Any]]
    production: Sequence[Mapping[str, Any]] = ()  # production v3 conversations (contract shape), for pairing
    start_state: Any = None
    overlay: Overlay = field(default_factory=Overlay)
    config: LabStackConfig | None = None
    embedder: Any = None
    vector_index: Any = None
    reset_user: bool = True
    day: str | None = None
    tz_name: str | None = None
    production_recap_at: Any = None
    arrival_mode: str = 'production'
    arrival_lag: timedelta = DEFAULT_LAG
    partial_step: timedelta | None = None  # live transcript writes before the capture ends (v3/feed.py)
    partial_lag: timedelta = DEFAULT_LAG
    tail: timedelta = timedelta(hours=2)
    sweeps: bool = True
    max_events: int = 20000
    clock: str = 'sim'  # sim | tick (stack/clock.py CLOCK_MODES)


def lab_overlay(overlay: Overlay) -> Overlay:
    """The run overlay plus the loopback reconcile base URL (never contacted)."""
    env = dict(overlay.env)
    env.setdefault(TASKS_URL_ENV, LOOPBACK_TASKS_URL)
    return replace(overlay, env=env)


def export_conversations(
    run_dir: Path,
    *,
    uid: str,
    derived: Sequence[Mapping[str, Any]],
    production: Sequence[Mapping[str, Any]],
    store: Any,
    sinks: Any,
) -> list[dict[str, Any]]:
    people = store.people_names(uid)
    calls = llm_call_ids_by_conversation(Path(run_dir) / 'llm_calls.jsonl')
    pairs = pair_by_recordings(derived, production)
    out = []
    for row in derived:
        cid = str(row['id'])
        recordings = [str(r) for r in row.get('v3_recording_ids') or []]
        call_ids = list(calls.get(cid, []))
        for rid in recordings:
            call_ids.extend(calls.get(rid, []))
        baseline_id, baseline_ids = pairs.get(cid, (None, []))
        payload = normalize_v3_conversation(
            row,
            action_items=store.action_items_for(uid, cid),
            memories=store.memories_for(uid, cid),
            notifications=sinks.notifications_for(cid),
            llm_call_ids=sorted(set(call_ids)),
            people=people,
            baseline_id=baseline_id,
            baseline_ids=baseline_ids,
        )
        write_json(Path(run_dir) / 'conversations' / f'{cid}.json', payload)
        out.append(payload)
    return out


def replayed_rows(
    derived: Sequence[Mapping[str, Any]], replayed: set[str], day_start: datetime, day_end: datetime | None = None
) -> list[Mapping[str, Any]]:
    """The v3 conversations this replay planned: any that holds a replayed recording or starts in the day.
    Start-state conversations from earlier days stay out of the run's output, and so do conversations
    starting at or after ``day_end``: production's baseline keeps only v3 conversations starting in the
    day (``v3/corpus.py``), so a recording that runs past midnight would otherwise show its next-day
    part as replay-only."""
    out = []
    for row in derived:
        started = parse_time(row.get('started_at'))
        if day_end is not None and started is not None and started >= day_end:
            continue
        if replayed & {str(r) for r in row.get('v3_recording_ids') or []} or (started and started >= day_start):
            out.append(row)
    return out


def recording_fate(
    recordings: Sequence[Mapping[str, Any]],
    derived: Sequence[Mapping[str, Any]],
    words: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Where each replayed recording's speech went (claims and the conversations listing it).

    ``words``: the fed word count per recording (the plan's), else counted from the stored row.
    """
    listed: dict[str, list[str]] = {}
    for row in derived:
        for rid in row.get('v3_recording_ids') or []:
            listed.setdefault(str(rid), []).append(str(row['id']))
    rows = []
    for rec in recordings:
        rid = str(rec['id'])
        rows.append(
            {
                'id': rid,
                'started_at': rec.get('started_at'),
                'finished_at': rec.get('finished_at'),
                'status': rec.get('status'),
                'pending': bool(rec.get('v3_pending')),
                'conversations': sorted(set(listed.get(rid, []))),
                'claims': len(rec.get('claims') or []),
                'words': words[rid] if words is not None and rid in words else word_count(rec),
            }
        )
    return {
        'recordings': len(rows),
        'unclaimed': sum(1 for r in rows if not r['conversations']),
        'unclaimed_without_speech': sum(1 for r in rows if not r['conversations'] and not r['words']),
        'still_pending': sum(1 for r in rows if r['pending']),
        'rows': rows,
    }


async def replay_v3(spec: V3RunSpec) -> dict[str, Any]:
    from testing.pipeline_lab.seed.writer import ProductSeedWriter, reset_lab_state, seed_start_state
    from testing.pipeline_lab.vector import install_vector_index
    from testing.pipeline_lab.vector.embed import install_embeddings
    from testing.pipeline_lab.vector.seed import apply_with_product, plan_vectors

    if spec.vector_index is None:
        raise ValueError('a vector index is required (DESIGN L7)')
    config = spec.config or LabStackConfig.from_env()
    run_dir = Path(spec.run_dir)
    clock = LabClock.for_mode(spec.day_start, spec.clock)
    plan = plan_arrivals(
        spec.recordings,
        lag=spec.arrival_lag,
        mode=spec.arrival_mode,
        partial_step=spec.partial_step,
        partial_lag=spec.partial_lag,
    )
    result: dict[str, Any] = {'plan': plan.summary(), 'warnings': [], 'clock': clock.mode}
    timings: dict[str, float] = {}
    result['timings'] = timings
    mark = [time.perf_counter()]

    def phase(name: str) -> None:
        now = time.perf_counter()
        timings[name] = round(now - mark[0], 3)
        mark[0] = now

    trace_target = os.environ.get(TRACE_ENV)
    with lab_environment(
        config, lab_overlay(spec.overlay), run_dir=run_dir, preimport=PRODUCT_MODULES + V3_MODULES
    ) as env, ExitStack() as stack:
        install_vector_index(stack, spec.vector_index)
        if spec.embedder is not None:
            install_embeddings(stack, spec.embedder)
        sinks = CaptureSinks(
            run_dir=run_dir, clock=clock.now, allowed_ports=config.loopback_ports(), proxy_url=config.llm_proxy_url
        ).install(stack)
        barrier = ExecutorBarrier()
        result['executors'] = barrier.instrument_product(stack)
        _record_processing_failures(stack, run_dir / 'processing_errors.log')
        tasks = LoopbackTasks(clock.now, log=lambda row: append_jsonl(run_dir / 'v3_tasks.jsonl', row))
        result['tasks_bound'] = tasks.install(stack)
        install_attribution(stack)
        install_emulator_size_errors(stack)
        install_planner_trace(stack, trace_target)
        stack.enter_context(installed_clock(clock, product_monotonic=clock.mode == 'sim'))
        if any(d.get('name') == 'typesense_unavailable' for d in env.decisions.rows):
            result['warnings'].append('typesense not listening: conversation index writes off for this run')
        phase('environment')
        if spec.start_state is not None:
            writer = ProductSeedWriter(env.firestore)
            reset = (lambda: reset_lab_state(env.firestore, env.redis, config.uid)) if spec.reset_user else None
            result['seed'] = seed_start_state(spec.start_state, writer, reset=reset)
            result['warnings'].extend(result['seed'].get('warnings') or [])
            phase('seed')
            records, vector_report = plan_vectors(
                config.uid,
                conversations=spec.start_state.conversations,
                memories=spec.start_state.memories,
                action_items=spec.start_state.action_items,
            )
            result['vectors'] = apply_with_product(records, config.uid, vector_report).as_dict()
            phase('seed_vectors')
        try:
            admission = admit(config.uid)
            env.decisions.record('conversations_v3_admission', admission['admitted'], 'lab_admission_markers')
            result['admission'] = admission
            if not admission['admitted']:
                raise RuntimeError('the lab uid is not admitted to conversations v3 under this overlay')
            ops = ProductV3Ops(finalizer=ProductFinalizer(env.firestore), barrier=barrier)
            driver = V3Driver(
                uid=config.uid,
                ops=ops,
                tasks=tasks,
                clock=clock,
                horizon=default_horizon(plan.arrivals, spec.day_end, spec.tail),
                max_events=spec.max_events,
                sweeps=spec.sweeps,
            )
            report = await driver.run(plan.arrivals)
            phase('driver')
            late = clock.late_monotonic_reads
            result['late_monotonic_reads'] = late
            if late:
                # Real time reached a product decision: this run may not repeat (stack/clock.py).
                report.warnings.append(f'clock: {late} product monotonic reads past the per-event grace')
            write_json(
                run_dir / 'v3_driver.json',
                {
                    'clock': clock.mode,
                    'late_monotonic_reads': late,
                    'plan': plan.summary(),
                    'arrivals': [
                        {
                            'recording_id': a.recording_id,
                            'instant': a.instant.isoformat(),
                            'instant_source': a.instant_source,
                            'words': a.words,
                            'backfill_donor': a.backfill_donor,
                            'manual_end': a.manual_end,
                            **({'segments': a.segments} if a.partial else {}),
                        }
                        for a in plan.arrivals
                    ],
                    'skipped': plan.skipped,
                    'tasks': {'created': tasks.created, 'duplicates': tasks.duplicates, 'left': tasks.pending()},
                    **report.as_dict(),
                },
            )
            result['driver'] = report.summary()
            derived, recordings = read_v3_rows(config.uid)
            derived_all = derived
            derived = replayed_rows(derived, {a.recording_id for a in plan.arrivals}, spec.day_start, spec.day_end)
            exported = export_conversations(
                run_dir,
                uid=config.uid,
                derived=derived,
                production=spec.production,
                store=ProductChainStore(),
                sinks=sinks,
            )
            # Only the day's replayed recordings: earlier days' recordings are start state, claimed by earlier rows.
            replayed = {a.recording_id for a in plan.arrivals}
            fate = recording_fate(
                [r for r in recordings if str(r.get('id')) in replayed],
                derived_all,  # a claim by a next-day conversation still claims the recording
                words={a.recording_id: a.words for a in plan.arrivals if not a.partial},
            )
            write_json(run_dir / 'v3_recordings.json', fate)
            write_json(
                run_dir / 'chain.json',
                {
                    'summary': {
                        'status': report.summary()['status'],
                        'conversations': len(exported),
                        'failed': sum(1 for c in exported if c['v3']['process_failed']),
                        'exported': len(exported),
                    },
                    'pipeline': 'v3',
                    'conversations': [
                        {
                            'conversation_id': c['id'],
                            'status': 'failed' if c['v3']['process_failed'] else 'ok',
                            'lane': 'v3',
                        }
                        for c in exported
                    ],
                    'warnings': report.warnings,
                },
            )
            result['conversations'] = {
                'v3': len(exported),
                'visible': sum(1 for c in exported if c['v3']['visible']),
                'unclaimed_recordings': fate['unclaimed'],
            }
            phase('export')
            if spec.day is not None:
                from testing.pipeline_lab.day.run import run_day

                kept = [str(r['id']) for r in derived if home_visible(r)]
                day_payload = run_day(
                    uid=config.uid,
                    day=spec.day,
                    tz_name=spec.tz_name,
                    run_dir=run_dir,
                    clock=clock,
                    sinks=sinks,
                    memories_before=spec.start_state.memories if spec.start_state is not None else (),
                    goals_before=spec.start_state.goals if spec.start_state is not None else (),
                    kept_conversation_ids=kept,
                    vector_index=spec.vector_index,
                    production_recap_at=spec.production_recap_at,
                )
                result['day'] = {
                    'recap': day_payload.get('recap'),
                    'chat_index_ready': day_payload['chat_index'].get('ready'),
                }
                phase('day')
        finally:
            clear_admission(config.uid)  # never leave the app-capability markers behind
        result['notifications'] = len(sinks.notifications)
        result['network_refusals'] = list(env.network.refusals)
        if getattr(spec.vector_index, 'path', None):
            spec.vector_index.save()
    return result
