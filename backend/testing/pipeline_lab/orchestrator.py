"""Run orchestration: walk the stages in order, consult the stage cache, record timings and status.

``run_pipeline`` creates ``runs/<run_id>/run.json``, opens the run's spend ledger,
optionally starts the LLM proxy (its URL goes into the arm env as
``OMI_LLM_GATEWAY_URL``), then for each selected stage:

- computes the L12 key from the corpus day hash, every earlier stage's output
  hash, the driver's own ``inputs(ctx)``, the backend tree, overlay and model config;
- serves a cacheable stage from ``cache/<stage>/`` when the key hits and the stage
  is before ``--from-stage`` (``restore`` rewrites run files from the manifest);
- otherwise calls the registered driver and caches its output manifest.

"Re-run from stage X" therefore re-runs X and everything after it; unchanged LLM
calls inside those stages are still served by the proxy cache. A driver that
cannot be restored from a manifest (its effect is emulator state) sets
``cacheable = False`` and always runs.

Stages before ``--from-stage`` are served from the cache when an entry exists and
are otherwise marked ``skipped``: in M1 ``--from-stage discard`` starts the chain
from the stored production transcripts (RULINGS 16).

Stops: a ledger refusal (or the proxy reporting the cap) marks the run
``stopped`` (exit 4); any other driver error marks it ``failed`` (exit 2) with the
traceback in ``runs/<run_id>/errors.log``.
"""

from __future__ import annotations

import os
import re
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from testing.pipeline_lab import keys, worktrees
from testing.pipeline_lab.contracts import (
    STAGES,
    CorpusDay,
    Decision,
    RunRecord,
    RunStatus,
    StageRun,
    StageState,
    stage_index,
    utc_iso,
)
from testing.pipeline_lab.ledger import DEFAULT_BUDGET_USD, SpendCapReached, SpendLedger
from testing.pipeline_lab.registry import DriverNotRegistered, Registry, StageResult
from testing.pipeline_lab.store import Store, atomic_write_bytes, new_run_id

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_TRANSPORT = 3
EXIT_SPEND = 4
UPSTREAM_TOKEN_ENV = 'OMI_PIPELINE_LAB_UPSTREAM_TOKEN'

_SECRETISH = re.compile(r'(TOKEN|SECRET|PASSWORD|API_KEY|CREDENTIAL|PRIVATE)', re.IGNORECASE)


def redact_overlay(overlay: Mapping[str, Any]) -> dict[str, Any]:
    """The overlay as recorded in run.json: secret-shaped env values replaced by a hash prefix."""
    out = dict(overlay)
    env = dict(out.get('env') or {})
    for name, value in env.items():
        if _SECRETISH.search(name):
            env[name] = 'redacted:' + keys.sha256_hex(str(value).encode())[:8]
    if env:
        out['env'] = env
    return out


def select_stages(stages: Optional[Sequence[str]]) -> list[str]:
    if not stages:
        return list(STAGES)
    for stage in stages:
        stage_index(stage)
    return [stage for stage in STAGES if stage in set(stages)]


@dataclass
class RunRequest:
    day_id: str
    ref: str
    overlay: dict[str, Any] = field(
        default_factory=dict
    )  # stack.overlay schema: {name, env, model_config, serving, gates, strict}
    from_stage: Optional[str] = None
    stages: Optional[list[str]] = None
    budget_usd: float = DEFAULT_BUDGET_USD
    allow_missing: bool = False
    no_cache: bool = False
    llm_upstream: Optional[str] = None
    llm_mode: str = 'record'
    llm_prices: Optional[dict[str, Any]] = None
    run_id: Optional[str] = None
    allow_lock_mismatch: bool = False
    engine: str = 'product'  # chain engine: 'product' (real backend, local stack) or 'fake' (hermetic tests)
    commit: Optional[str] = None  # resolved sha when the run uses an unpinned in-place checkout


@dataclass
class StageContext:
    """Everything a driver gets. Drivers run product code through ``run_arm``."""

    store: Store
    run_id: str
    day: CorpusDay
    stage: str
    worktree: Optional[worktrees.Worktree]
    backend_tree: str
    overlay: dict[str, Any]
    env: dict[str, str]
    ledger: SpendLedger
    upstream: dict[str, dict[str, Any]]
    llm_proxy_url: Optional[str] = None
    engine: str = 'product'
    arm_backend: Optional[Path] = None  # in-place runs: this checkout's backend/, run unpinned
    warnings: list[str] = field(default_factory=list)
    run_extra: dict[str, Any] = field(
        default_factory=dict
    )  # merged into run.json (e.g. the STT source shown in the UI)

    @property
    def model_config(self) -> dict[str, Any]:
        return dict(self.overlay.get('model_config') or {})

    @property
    def run_dir(self) -> Path:
        return self.store.run_dir(self.run_id)

    def item_key(self, item: str, inputs: Mapping[str, str], schema_version: int = 1) -> str:
        """L12 key for one item inside this stage (e.g. one conversation's notes)."""
        return keys.stage_key(
            f'{self.stage}:{item}',
            backend_tree=self.backend_tree,
            inputs=inputs,
            overlay={k: v for k, v in self.overlay.items() if k != 'model_config'},
            model_config=self.model_config,
            schema_version=schema_version,
        )

    def cache_get(self, key: str) -> Optional[dict[str, Any]]:
        return self.store.cache_get(self.stage, key)

    def cache_put(self, key: str, value: dict[str, Any]) -> None:
        self.store.cache_put(self.stage, key, value)

    def decision(self, name: str, mode: str, source: str) -> None:
        self.store.append_decisions(self.run_id, [Decision(at=utc_iso(), name=name, mode=mode, source=source)])

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def run_arm(self, module: str, args: Sequence[str] = (), *, timeout: Optional[float] = None, **kwargs: Any):
        if self.worktree is None:
            raise worktrees.WorktreeError('no pinned worktree for this run')
        return worktrees.run_arm(self.worktree.backend, module, args, overlay=self.env, timeout=timeout, **kwargs)

    def run_module(self, module: str, args: Sequence[str] = (), *, timeout: Optional[float] = None) -> int:
        """Run a lab entry module for this stage in a fresh ``python -I`` process: against the pinned
        arm, or against the in-place checkout's ``backend/``. Only runs with neither (tests that pass a
        bare ``backend_tree``) call ``main`` in this process, with ``env`` overlaid on ``os.environ``.

        A separate process matters: the chain installs a deny-by-default network guard and a
        process-wide clock, which must not reach the LLM proxy serving from this process.
        """
        backend = self.worktree.backend if self.worktree is not None else self.arm_backend
        if backend is not None:
            result = worktrees.run_arm(backend, module, args, overlay=self.env, timeout=timeout)
            log = (result.stderr or '') + (result.stdout or '')
            atomic_write_bytes(self.run_dir / f'{self.stage}.process.log', log.encode('utf-8', errors='replace'))
            return result.returncode
        import importlib
        import os
        from unittest import mock

        entry = importlib.import_module(module)
        with mock.patch.dict(os.environ, self.env):
            return int(entry.main(list(args)) or 0)


@dataclass
class RunOutcome:
    run: RunRecord
    exit_code: int
    error: Optional[str] = None


def _stage_inputs(day: CorpusDay, upstream: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    inputs = {'corpus_day': keys.hash_json(day.to_json())}
    for stage, output in upstream.items():
        inputs[f'stage:{stage}'] = keys.hash_json(output)
    return inputs


def run_pipeline_kind(store: Store, overlay: Mapping[str, Any], day_id: str) -> str:
    """``classic`` or ``v3``, as the chain stages will select it (``v3/select.py``); part of every stage key."""
    from testing.pipeline_lab.v3.corpus import day_has_v3
    from testing.pipeline_lab.v3.select import PipelineRefused, select_pipeline

    try:
        return select_pipeline(overlay or {}, day_has_v3=day_has_v3(store, day_id))[0]
    except PipelineRefused:
        return 'refused'  # the chain stage raises the real error when it runs


def run_pipeline(
    store: Store,
    request: RunRequest,
    registry: Registry,
    *,
    worktree: Optional[worktrees.Worktree] = None,
    backend_tree: Optional[str] = None,
    repo: Optional[Path] = None,
    in_place_repo: Optional[Path] = None,
) -> RunOutcome:
    """Execute one run. Pass ``worktree`` (or, in tests, only ``backend_tree``) or a ``repo`` to pin from."""
    from testing.pipeline_lab.stack.overlay import Overlay

    Overlay.from_mapping(request.overlay)  # one schema (RULINGS 7); raises on pins or raw cohort env
    day = store.read_day(request.day_id)
    selected = select_stages(request.stages)
    forced_from = stage_index(request.from_stage) if request.from_stage else None
    missing = registry.missing(selected)
    if missing and not request.allow_missing:
        raise DriverNotRegistered('stage driver', missing)
    if worktree is None and backend_tree is None:
        if repo is None:
            raise worktrees.WorktreeError('run needs a repo to pin the ref from')
        worktree = worktrees.ensure_worktree(repo, request.ref)
    tree = worktree.backend_tree if worktree is not None else str(backend_tree)
    pipeline = run_pipeline_kind(store, request.overlay, day.day_id)

    run_id = request.run_id or new_run_id(day.day_id, request.ref)
    run = RunRecord(
        run_id=run_id,
        day_id=day.day_id,
        ref=request.ref,
        commit=worktree.sha if worktree else request.commit,
        backend_tree=tree,
        overlay=redact_overlay(request.overlay),
        status=RunStatus.RUNNING.value,
        started_at=utc_iso(),
        budget_usd=request.budget_usd,
        stages={stage: StageRun() for stage in selected},
        extra={
            'from_stage': request.from_stage,
            'chain_engine': request.engine,
            'llm_mode': request.llm_mode if request.llm_upstream or request.llm_mode == 'replay' else None,
        },
    )
    if day.start_state_snapshot is None:
        run.warnings.append('corpus day has no start-state snapshot')
    if in_place_repo is not None:
        run.extra['in_place'] = True
        dirty = worktrees.git(Path(in_place_repo), 'status', '--porcelain', '--', 'backend')
        if dirty.strip():
            run.warnings.append('in-place run: backend/ has uncommitted changes, so backend_tree names HEAD only')
    if worktree is not None:
        try:
            worktrees.check_lockfile(worktrees.harness_package_dir().parents[1], worktree.backend)
        except worktrees.WorktreeError as drift:
            if not request.allow_lock_mismatch:
                raise  # RULINGS 11: fail closed; --allow-lock-mismatch downgrades to a warning
            run.warnings.append(str(drift))
    store.create_run(run)
    ledger = SpendLedger(store.ledger_path(run_id), budget_usd=request.budget_usd)
    env = {str(k): str(v) for k, v in (request.overlay.get('env') or {}).items()}

    proxy = None
    if request.llm_upstream or request.llm_mode == 'replay':
        from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
        from testing.pipeline_lab.llm_proxy.wire import PriceTable

        try:
            proxy = LlmProxy(
                ProxyConfig(
                    upstream=request.llm_upstream or 'http://127.0.0.1:9',
                    mode=request.llm_mode,
                    run_id=run_id,
                    prices=PriceTable.from_json(request.llm_prices or {}),
                    # The real gateway's credential, from the operator's env only (never run.json or disk).
                    upstream_token=os.environ.get(UPSTREAM_TOKEN_ENV) or None,
                ),
                store=store,
                ledger=ledger,
            ).start()
        except BaseException as failure:  # a bad upstream or a failed bind: never leave the run 'running'
            run.status = RunStatus.FAILED.value
            run.finished_at = utc_iso()
            run.warnings.append(f'llm proxy did not start: {type(failure).__name__}')
            store.write_run(run)
            raise
        env['OMI_LLM_GATEWAY_URL'] = proxy.url
        env['OMI_PIPELINE_LAB_LLM_PROXY_URL'] = proxy.url  # RULINGS 8: the name the chain's stack reads

    upstream: dict[str, dict[str, Any]] = {}
    exit_code, error = EXIT_OK, None
    walked = False
    try:
        for stage in selected:
            if stage not in registry.stages:
                run.stages[stage].status = StageState.NOT_REGISTERED.value
                run.warnings.append(f'stage driver not registered: {stage} (skipped)')
                store.write_run(run)
                continue
            driver = registry.stages[stage]
            ctx = StageContext(
                store=store,
                run_id=run_id,
                day=day,
                stage=stage,
                worktree=worktree,
                backend_tree=tree,
                overlay=request.overlay,
                env=dict(env),
                ledger=ledger,
                upstream=dict(upstream),
                llm_proxy_url=proxy.url if proxy else None,
                engine=request.engine,
                arm_backend=Path(in_place_repo) / 'backend' if in_place_repo is not None else None,
            )
            run.stages[stage].status = StageState.RUNNING.value
            store.write_run(run)
            started = time.monotonic()
            try:
                inputs = _stage_inputs(day, upstream)
                inputs['pipeline'] = pipeline  # a classic entry is never served to a v3 run, or back
                extra_inputs = getattr(driver, 'inputs', None)
                if extra_inputs is not None:
                    inputs.update({f'driver:{k}': v for k, v in extra_inputs(ctx).items()})
                key = keys.stage_key(
                    stage,
                    backend_tree=tree,
                    inputs=inputs,
                    overlay={k: v for k, v in request.overlay.items() if k != 'model_config'},
                    model_config=request.overlay.get('model_config') or {},
                    schema_version=int(getattr(driver, 'schema_version', 1)),
                )
                cacheable = bool(getattr(driver, 'cacheable', True)) and not request.no_cache
                forced = forced_from is not None and stage_index(stage) >= forced_from
                entry = store.cache_get(stage, key) if cacheable and not forced else None
                state = run.stages[stage]
                state.extra['key'] = key
                before_start = forced_from is not None and stage_index(stage) < forced_from
                if entry is None and before_start:
                    state.status = StageState.SKIPPED.value
                    run.warnings.append(f'{stage}: before --from-stage and not cached (skipped)')
                    continue
                if entry is not None:
                    restore = getattr(driver, 'restore', None)
                    if restore is not None:
                        restore(ctx, entry['output'])
                    output = entry['output']
                    state.status = StageState.CACHED.value
                    state.cache_hits += 1
                else:
                    result = driver.run(ctx)
                    if not isinstance(result, StageResult):
                        raise TypeError(f'{stage} driver returned {type(result).__name__}, expected StageResult')
                    output = result.output
                    if cacheable:
                        store.cache_put(stage, key, {'output': output, 'run_id': run_id})
                    state.status = StageState.COMPLETE.value
                    state.cache_hits += result.cache_hits
                    state.cache_misses += result.cache_misses
                    run.warnings.extend(f'{stage}: {w}' for w in result.warnings)
                upstream[stage] = output
                run.warnings.extend(f'{stage}: {w}' for w in ctx.warnings)
                run.extra.update(ctx.run_extra)
                if proxy is not None and proxy.cap_reached:
                    raise SpendCapReached('LLM proxy refused a call at the spend cap')
            except SpendCapReached as stop:
                run.stages[stage].status = StageState.FAILED.value
                exit_code, error = EXIT_SPEND, f'spend stop in {stage}: {stop}'
            except Exception as failure:  # noqa: BLE001 - recorded, then the run stops
                run.stages[stage].status = StageState.FAILED.value
                exit_code, error = EXIT_ERROR, f'{stage} failed: {type(failure).__name__}: {failure}'
                atomic_write_bytes(
                    store.run_dir(run_id) / 'errors.log', traceback.format_exc().encode('utf-8', errors='replace')
                )
            finally:
                run.timings[stage] = round(time.monotonic() - started, 3)
                run.spend_usd = round(ledger.spent(), 6)
                store.write_run(run)
            if exit_code != EXIT_OK:
                break
        walked = True
    finally:
        if not walked and exit_code == EXIT_OK:
            exit_code, error = EXIT_ERROR, 'run interrupted'
        if proxy is not None:
            proxy.stop()
        run.spend_usd = round(ledger.spent(), 6)
        run.finished_at = utc_iso()
        if exit_code == EXIT_OK:
            run.status = RunStatus.COMPLETE.value
        elif exit_code == EXIT_SPEND:
            run.status = RunStatus.STOPPED.value
        else:
            run.status = RunStatus.FAILED.value
        if error:
            run.warnings.append(error)
        store.write_run(run)
    return RunOutcome(run=run, exit_code=exit_code, error=error)
