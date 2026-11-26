"""Compose the chain lane into one call the CLI (lane ``core``) can make.

    report = asyncio.run(replay_chain(ChainRunSpec(...)))

Order inside the environment matters: product modules are imported *before* the
lab clock is installed (so no model class is defined against the lab datetime
type), then the vector index, embeddings, capture sinks and executor barrier are
installed, the start state is seeded, and the ordered driver runs.

The chain runs on the simulated clock by default (``stack/clock.py``, mode ``sim``): product code
sees the instant the driver set for each conversation, and its monotonic and loop clocks follow
the replay (``product_monotonic=True``), so the same inputs stamp the same instants however fast the
host is. The overlay switch the v3 replay uses, ``model_config.v3.clock: "tick"``, restores the
ticking clock here too (:func:`chain_clock_mode`). ``late_monotonic_reads`` in the result counts
product monotonic reads past the per-event grace (a place real time reached a product decision).
"""

from __future__ import annotations

import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from testing.pipeline_lab.chain.barrier import ExecutorBarrier
from testing.pipeline_lab.chain.driver import ChainDriver, ProductChainStore, ProductFinalizer
from testing.pipeline_lab.chain.order import plan_chain
from testing.pipeline_lab.sinks.capture import CaptureSinks
from testing.pipeline_lab.stack.clock import LabClock, installed_clock
from testing.pipeline_lab.stack.config import LabStackConfig
from testing.pipeline_lab.stack.env import lab_environment
from testing.pipeline_lab.stack.overlay import Overlay

# Imported before the clock goes in. Keep this list to modules the chain reaches.
PRODUCT_MODULES = (
    'utils.conversations.process_conversation',
    'utils.conversations.finalizer',
    'utils.conversations.lifecycle',
    'database.conversation_finalization_jobs',
    'database.vector_db',
    'utils.notifications',
    'utils.webhooks',
    'utils.task_sync',
    'utils.app_integrations',
    'utils.other.notifications',
    'utils.llm.goals',
)


def chain_clock_mode(overlay: Any) -> str:
    """``sim`` unless the overlay's ``model_config.v3.clock`` asks for ``tick`` (one switch for both replays)."""
    from testing.pipeline_lab.stack.clock import CLOCK_MODES

    raw = dict((getattr(overlay, 'model_config', None) or {}).get('v3') or {})
    mode = str(raw.get('clock') or 'sim')
    if mode not in CLOCK_MODES:
        raise ValueError(f'model_config.v3.clock must be one of {CLOCK_MODES}, got {mode!r}')
    return mode


@dataclass
class ChainRunSpec:
    run_dir: Path
    day_start: datetime
    conversations: Sequence[Mapping[str, Any]]
    start_state: Any = None  # seed.start_state.StartState; None = already seeded
    overlay: Overlay = field(default_factory=Overlay)
    config: LabStackConfig | None = None
    embedder: Any = None  # vector.embed.Embedder; None = product embeddings via the proxy
    vector_index: Any = None  # vector.index.NumericVectorIndex; required
    reset_user: bool = True
    export_workers: int = 4
    day: str | None = None  # YYYY-MM-DD local; when set, the day stages run after the chain
    tz_name: str | None = None
    clock: str | None = None  # sim | tick; None = chain_clock_mode(overlay)
    production_recap_at: Any = None


def _record_processing_failures(stack: ExitStack, path: Path) -> None:
    """The product logs only the exception class of a failed ``process_conversation``; keep the
    full traceback in the run's private store so a failed conversation can be diagnosed."""
    import traceback

    from testing.pipeline_lab.stack.io import append_jsonl
    from testing.pipeline_lab.stack.patching import replace_everywhere
    from utils.llm import gateway_error_contract

    original = gateway_error_contract.conversation_processing_http_exception

    def recorded(error: BaseException, *args: Any, **kwargs: Any) -> Any:
        append_jsonl(
            path,
            {
                'error': type(error).__name__,
                'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
            },
        )
        return original(error, *args, **kwargs)

    replace_everywhere(stack, original, recorded)


async def replay_chain(spec: ChainRunSpec) -> dict[str, Any]:
    from testing.pipeline_lab.vector import install_vector_index
    from testing.pipeline_lab.vector.embed import install_embeddings
    from testing.pipeline_lab.vector.seed import apply_with_product, plan_vectors
    from testing.pipeline_lab.seed.writer import ProductSeedWriter, reset_lab_state, seed_start_state

    if spec.vector_index is None:
        raise ValueError('a vector index is required (DESIGN L7); refusing to run with an empty Pinecone stub')
    config = spec.config or LabStackConfig.from_env()
    clock = LabClock.for_mode(spec.day_start, spec.clock or chain_clock_mode(spec.overlay))
    result: dict[str, Any] = {'clock': clock.mode}
    # Wall seconds per phase (``environment`` includes importing the product modules).
    timings: dict[str, float] = {}
    result['timings'] = timings
    mark = time.monotonic()

    def lap(name: str) -> None:
        nonlocal mark
        now = time.monotonic()
        timings[name] = round(timings.get(name, 0.0) + now - mark, 3)
        mark = now

    with lab_environment(
        config, spec.overlay, run_dir=spec.run_dir, preimport=PRODUCT_MODULES
    ) as env, ExitStack() as stack:
        install_vector_index(stack, spec.vector_index)
        if spec.embedder is not None:
            install_embeddings(stack, spec.embedder)
        sinks = CaptureSinks(
            run_dir=spec.run_dir,
            clock=clock.now,
            allowed_ports=config.loopback_ports(),
            proxy_url=config.llm_proxy_url,
        ).install(stack)
        barrier = ExecutorBarrier()
        result['executors'] = barrier.instrument_product(stack)
        _record_processing_failures(stack, Path(spec.run_dir) / 'processing_errors.log')
        stack.enter_context(installed_clock(clock, product_monotonic=clock.mode == 'sim'))
        lap('environment')
        if spec.start_state is not None:
            writer = ProductSeedWriter(env.firestore)
            reset = (lambda: reset_lab_state(env.firestore, env.redis, config.uid)) if spec.reset_user else None
            result['seed'] = seed_start_state(spec.start_state, writer, reset=reset)
            records, vector_report = plan_vectors(
                config.uid,
                conversations=spec.start_state.conversations,
                memories=spec.start_state.memories,
                action_items=spec.start_state.action_items,
            )
            result['vectors'] = apply_with_product(records, config.uid, vector_report).as_dict()
        lap('seed')
        driver = ChainDriver(
            uid=config.uid,
            store=ProductChainStore(),
            finalizer=ProductFinalizer(env.firestore),
            clock=clock,
            barrier=barrier,
            sinks=sinks,
            run_dir=spec.run_dir,
            export_workers=spec.export_workers,
        )
        report = await driver.run(plan_chain(spec.conversations))
        result['chain'] = report.as_dict()
        lap('conversations')
        timings['conversations_export'] = round(report.export_seconds, 3)
        if spec.day is not None:
            from testing.pipeline_lab.day.run import run_day
            from testing.pipeline_lab.stack.io import read_json

            kept = []
            for path in sorted((Path(spec.run_dir) / 'conversations').glob('*.json')):
                payload = read_json(path)
                if not payload.get('discarded'):
                    kept.append(payload['id'])
            day_payload = run_day(
                uid=config.uid,
                day=spec.day,
                tz_name=spec.tz_name,
                run_dir=spec.run_dir,
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
            lap('day')
        result['late_monotonic_reads'] = clock.late_monotonic_reads
        result['notifications'] = len(sinks.notifications)
        result['egress'] = len(sinks.egress)
        result['network_refusals'] = list(env.network.refusals)
        if getattr(spec.vector_index, 'path', None):
            spec.vector_index.save()
    lap('teardown')
    return result
