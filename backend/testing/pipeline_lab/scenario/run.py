"""Run one scenario through the real v3 code on the local stack, in this process.

    python -m testing.pipeline_lab.scenario.run --file SCENARIO.json --out DIR

Normally started by ``python -m testing.pipeline_lab scenario run`` (``scenario/stack.py``), once per
scenario in a fresh process, with ``FIRESTORE_EMULATOR_HOST`` and ``OMI_PIPELINE_LAB_REDIS`` naming a
loopback emulator and Redis. Same lab environment as a day replay (``v3/run.py``): the virtual clock, the
loopback Cloud Tasks queue, capture-only sinks, the in-process vector index with the fake embedder, the
lab's scripted fake LLM gateway, and the production flag profile of this checkout
(``deploy/runtime_env.yaml``, service ``backend-sync``) with the scenario's ``env`` on top.

Writes ``DIR/result.json`` (outside git) and prints the same JSON as its last stdout line.

Isolation (set by the parent, ``scenario/stack.py``): ``OMI_PIPELINE_LAB_PROJECT_ID`` names this run's own
``demo-lab-<run id>`` Firestore project, ``OMI_PIPELINE_LAB_REDIS_DB`` the Redis database it leased, and
``OMI_PIPELINE_LAB_REDIS_LEASE`` the run id holding that lease; the reset clears only that database.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback
from typing import Any, Optional, Sequence

from testing.pipeline_lab.scenario.checks import OUTCOMES, evaluate, outcome
from testing.pipeline_lab.scenario.home import HOME_MODULES, HomeRecorder
from testing.pipeline_lab.scenario.spec import Scenario, load_scenario, plan_events

FAST_FINISH_ENV = 'CONVERSATIONS_V3_FAST_FINISH'
RUNTIME_ENV = Path(__file__).resolve().parents[3] / 'deploy' / 'runtime_env.yaml'
REDIS_LEASE_ENV = 'OMI_PIPELINE_LAB_REDIS_LEASE'


def product_runtime_env() -> Path:
    """``deploy/runtime_env.yaml`` of the product tree on ``sys.path`` (a compare arm's, not the lab's)."""
    spec = importlib.util.find_spec('database')
    if spec is not None and spec.origin:
        candidate = Path(spec.origin).resolve().parents[1] / 'deploy' / 'runtime_env.yaml'
        if candidate.exists():
            return candidate
    return RUNTIME_ENV


def scenario_overlay(scenario: Scenario, runtime_env: Path = RUNTIME_ENV) -> Any:
    """Production's backend-sync profile at this checkout, then fast finish per the scenario, then its env."""
    from testing.pipeline_lab.stack.overlay import Overlay
    from testing.pipeline_lab.stack.runtime_env import overlay_from_runtime_env
    from testing.pipeline_lab.v3.run import lab_overlay

    payload, _ = overlay_from_runtime_env(runtime_env, environment='prod', service='backend-sync')
    env = dict(payload.get('env') or {})
    if scenario.finish is not None:
        env[FAST_FINISH_ENV] = 'on' if scenario.finish.fast_finish else 'off'
    env.update(scenario.env)
    payload = {**payload, 'env': env, 'name': f'scenario:{scenario.name}'}
    return lab_overlay(Overlay.from_mapping(payload))


def seed_account(uid: str) -> str:
    """The account document production always has (the reset removes it): sync on, through the product's
    own settings writer. The batch privacy fence refuses a missing account (``account_missing``)."""
    from database import users as users_db

    users_db.set_user_private_cloud_sync_enabled(uid, True)
    return 'private_cloud_sync_enabled'


async def run_scenario(
    scenario: Scenario,
    out_dir: Path,
    *,
    llm_url: str,
    tick: bool = True,
    audio: Optional[dict] = None,
    trace_calls: bool = False,
) -> dict[str, Any]:
    from testing.pipeline_lab.chain.barrier import ExecutorBarrier
    from testing.pipeline_lab.chain.driver import ProductFinalizer
    from testing.pipeline_lab.chain.run import PRODUCT_MODULES, _record_processing_failures
    from testing.pipeline_lab.scenario.ops import SCENARIO_MODULES, ScenarioOps
    from testing.pipeline_lab.seed.writer import reset_lab_state
    from testing.pipeline_lab.sinks.capture import CaptureSinks
    from testing.pipeline_lab.stack.clock import LabClock, installed_clock
    from testing.pipeline_lab.stack.config import LabStackConfig
    from testing.pipeline_lab.stack.env import lab_environment
    from testing.pipeline_lab.stack.io import append_jsonl
    from testing.pipeline_lab.v3.driver import V3Driver
    from testing.pipeline_lab.v3.product import V3_MODULES, admit, clear_admission, install_emulator_size_errors
    from testing.pipeline_lab.v3.tasks import LoopbackTasks
    from testing.pipeline_lab.vector import install_vector_index
    from testing.pipeline_lab.vector.embed import FakeEmbedder, install_embeddings
    from testing.pipeline_lab.vector.index import NumericVectorIndex

    config = replace(LabStackConfig.from_env(), llm_proxy_url=llm_url, lab_root=out_dir / 'lab')
    redis_lease = os.environ.get(REDIS_LEASE_ENV) or None  # read now: the lab environment clears os.environ
    events = plan_events(scenario)
    start = min(scenario.t0, events[0].instant) - timedelta(seconds=1)
    clock = LabClock(start, tick=tick)
    timings: dict[str, float] = {}
    mark = time.perf_counter()
    result: dict[str, Any] = {'scenario': scenario.name, 'timings': timings}
    embedder = FakeEmbedder(3072)
    index = NumericVectorIndex(dimension=embedder.dimension)
    with lab_environment(
        config,
        scenario_overlay(scenario, product_runtime_env()),
        run_dir=out_dir,
        preimport=PRODUCT_MODULES + V3_MODULES + SCENARIO_MODULES + HOME_MODULES,
    ) as env, ExitStack() as stack:
        install_vector_index(stack, index)
        install_embeddings(stack, embedder)
        sinks = CaptureSinks(
            run_dir=out_dir, clock=clock.now, allowed_ports=config.loopback_ports(), proxy_url=config.llm_proxy_url
        ).install(stack)
        barrier = ExecutorBarrier()
        barrier.instrument_product(stack)
        _record_processing_failures(stack, out_dir / 'processing_errors.log')
        tasks = LoopbackTasks(clock.now, log=lambda row: append_jsonl(out_dir / 'v3_tasks.jsonl', row))
        tasks.install(stack)
        install_emulator_size_errors(stack)
        stack.enter_context(installed_clock(clock))
        # --trace-calls (scenario/reach.py): files with a function called from here to the final snapshot.
        trace = None
        if trace_calls:
            from testing.pipeline_lab.scenario.reach import CallTrace

            trace = CallTrace().start()
        if audio:  # audio_file recordings: their words through the lab's batch/sync lane code (scenario/audio.py)
            from testing.pipeline_lab.scenario.audio import materialize

            scenario, result['audio'] = materialize(scenario, audio)
        # Home (home.json): the product's own Home routes, called by ops before each checkpoint's snapshot
        # and here before the final one, inside this run's isolated emulator project and Redis database.
        home = HomeRecorder(uid=config.uid, out_dir=out_dir, offset=scenario.offset, now=clock.now)
        ops = ScenarioOps(
            scenario=scenario,
            firestore=env.firestore,
            finalizer=ProductFinalizer(env.firestore),
            barrier=barrier,
            home=home,
        )
        ops.install(stack)
        ops.stt_sources = {row['label']: row['source'] for row in (result.get('audio') or {}).get('recordings', [])}
        clock.set(start)
        reset_lab_state(env.firestore, env.redis, config.uid, redis_lease=redis_lease)
        result['account'] = seed_account(config.uid)
        timings['environment'] = round(time.perf_counter() - mark, 3)
        mark = time.perf_counter()
        try:
            admission = admit(config.uid)
            if not admission['admitted']:
                raise RuntimeError('the lab uid is not admitted to conversations v3 under this overlay')
            horizon = max(e.instant for e in events) + (scenario.at(scenario.tail_seconds) - scenario.t0)
            clock.set(start)  # setup took real time on a ticking clock
            driver = V3Driver(uid=config.uid, ops=ops, tasks=tasks, clock=clock, horizon=horizon, sweeps=True)
            report = await driver.run(events)  # type: ignore[arg-type] - scenario events quack like arrivals
            timings['driver'] = round(time.perf_counter() - mark, 3)
            await asyncio.to_thread(home.write_home_snapshot, None)  # before the final snapshot reads on_home
            final = ops.snapshot(config.uid)
            recordings = ops.recordings(config.uid)
        finally:
            clear_admission(config.uid)
            if trace is not None:
                from testing.pipeline_lab.scenario.reach import CALLED_FILE

                (out_dir / CALLED_FILE).write_text(json.dumps(trace.stop(), indent=0) + '\n')
    results = []
    for index_, check in enumerate(scenario.checks):
        if check.at is not None:
            seen = ops.checkpoints.get(index_)
            results.append(seen['result'] if seen else evaluate(check, [], ops.finish_label))
        else:
            results.append(evaluate(check, final, ops.finish_label))
    errors = [e for e in report.events if e.outcome == 'error']
    result.update(
        outcome=outcome(
            scenario,
            results,
            error='event errors' if errors else ('home route failed' if home.failures() else None),
        ),
        finish_target=ops.finish_label,
        checks=[r.as_dict() for r in results],
        expected_failure=scenario.expected_failure,
        timeline=[
            {
                't': scenario.offset(_parse(e.at)),
                'kind': e.detail.get('instant_source') if e.kind == 'arrival' else e.kind,
                'ref': _short_ref(e.ref),
                'outcome': e.outcome,
                **({'error': e.error, 'where': e.detail.get('where')} if e.error else {}),
                **{k: v for k, v in e.detail.items() if k not in ('where', 'instant_source', 'left_running')},
            }
            for e in report.events
        ],
        conversations=final,
        checkpoints={
            str(i): {'t': scenario.checks[i].at, 'conversations': seen['snapshot']}
            for i, seen in sorted(ops.checkpoints.items())
        },
        recordings=recordings,
        fast_finish=ops.fast_finish_outcomes,
        stand_ins=ops.stand_ins,
        stand_in_sources=ops.stand_in_sources,
        home=home.summary(),
        driver=report.summary(),
        warnings=report.warnings,
        notifications=len(sinks.notifications),
        network_refusals=len(env.network.refusals),
    )
    from testing.pipeline_lab.scenario.standins import audio_steps, stand_in_notes

    result.update(stand_in_notes=stand_in_notes(result), audio_steps=audio_steps(result))
    return result


def _parse(at: str) -> datetime:
    return datetime.fromisoformat(at)


def _short_ref(ref: str) -> str:
    # Task names carry a hash of the lab uid and a minute; the minute is enough to read the timeline.
    return 'reconcile' if ref.startswith('conversations-v3-') else ref


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab.scenario.run')
    parser.add_argument('--file', required=True)
    parser.add_argument('--out', required=True, help='output directory (outside git)')
    parser.add_argument('--clock', choices=('frozen', 'tick'), default='frozen')
    parser.add_argument('--stt', choices=('replay', 'record-vendor', 'record-local'), default='replay')
    parser.add_argument('--stt-budget-usd', type=float, default=None)
    parser.add_argument('--trace-calls', action='store_true', help='write called_files.json (scenario/reach.py)')
    args = parser.parse_args(argv)
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        print(json.dumps({'outcome': 'error', 'error': 'FIRESTORE_EMULATOR_HOST must name a loopback emulator'}))
        return OUTCOMES['error']
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.perf_counter()
    from testing.pipeline_lab.scenario.audio import AudioError, prepare

    try:
        scenario = load_scenario(args.file)
        # Before the lab environment: recording on a miss may need the ambient env and network.
        audio = prepare(scenario, mode=args.stt, budget_usd=args.stt_budget_usd)
        from testing.pipeline_lab.llm_proxy.fake_upstream import FakeUpstream

        upstream = FakeUpstream().start()
        try:
            result = asyncio.run(
                run_scenario(
                    scenario,
                    out,
                    llm_url=upstream.url,
                    tick=args.clock == 'tick',
                    audio=audio,
                    trace_calls=args.trace_calls,
                )
            )
        finally:
            upstream.stop()
    except AudioError as error:
        result = {'scenario': Path(args.file).stem, 'outcome': 'error', 'error': str(error)}
    except Exception as error:  # noqa: BLE001 - reported as the scenario's error outcome
        (out / 'scenario_error.log').write_text(traceback.format_exc())
        result = {'outcome': 'error', 'error': type(error).__name__, 'log': str(out / 'scenario_error.log')}
    result['seconds'] = round(time.perf_counter() - started, 3)
    (out / 'result.json').write_text(json.dumps(result, indent=1, default=str))
    print(json.dumps(result, default=str))
    return OUTCOMES.get(result.get('outcome', 'error'), 2)


if __name__ == '__main__':
    sys.exit(main())
