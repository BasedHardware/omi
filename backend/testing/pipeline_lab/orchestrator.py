"""Run orchestration: walk the stages in order, consult the stage cache, record timings and status.

``run_pipeline`` creates ``runs/<run_id>/run.json``, opens the run's spend ledger,
optionally starts the LLM proxy (its URL goes into the arm env as
``OMI_LLM_GATEWAY_URL``), then walks the selected stages in **units**: a stage alone, or the
stages whose drivers share a ``unit`` (the chain composite, ``discard`` .. ``chat_index``),
which execute and are cached together. For each unit it:

- computes the L12 key from the corpus day hash, every earlier stage's output hash and stored
  artifact digest, the drivers' own ``inputs(ctx)``, the code (the backend tree with uncommitted
  in-place edits folded in, or for ``scoped_code`` drivers only the files the stage runs, from
  ``affected``), the overlay and model config (narrowed by a driver's ``key_overlay``);
- on a hit, writes the entry's stored artifacts back into the run directory, calls each driver's
  ``restore`` and marks the stages ``cached`` (no driver runs, no LLM call is made);
- otherwise runs the drivers and stores the outputs plus every run file they wrote (artifacts).

``--from-stage X`` re-runs the unit holding X and every unit after it (a unit is never split:
the run warns when X falls inside one); earlier units are served from the cache when an entry
exists and are otherwise marked ``skipped`` (``--from-stage discard`` then starts the chain from
the stored production transcripts, RULINGS 16). Unchanged LLM calls inside re-run stages are
still served by the proxy cache. ``--no-cache`` runs everything and stores nothing;
``--llm-mode refresh`` runs everything and stores the result. A driver's ``cache_ok(outputs)``
may refuse to store a result (the chain refuses one with failed conversations). The stage cache,
like the proxy cache, does not key on which LLM upstream answered.

Every stage gets a report row in ``run.json`` (``stages.<s>.report``): ``cache`` (hit, miss,
off, skipped, failed), seconds, LLM calls made during the stage split into upstream and
proxy-cache hits (a hit reports the ``saved_llm_calls`` of the stored run), and for the chain the
phase ``breakdown``. ``stage_report`` sums them, says when everything was a hit, and carries the
printable ``table`` the CLI shows.

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


# Run files the orchestrator (or the proxy) owns, and the run-wide append-only decision log (every
# stage adds to it, with timestamps); never stored as a stage's artifacts, so a hit does not restore
# the stored run's decisions.
RUN_FILES = frozenset({'run.json', 'ledger.json', 'llm_calls.jsonl', 'errors.log', 'decisions.jsonl'})


def _unit(driver: Any) -> str:
    """Stages whose drivers share a ``unit`` execute (and are cached) together; default: the stage alone."""
    return str(getattr(driver, 'unit', None) or driver.stage)


def _groups(selected: Sequence[str], registry: Registry) -> list[list[str]]:
    groups: list[list[str]] = []
    for stage in selected:
        driver = registry.stages.get(stage)
        if groups and driver is not None and groups[-1][-1] in registry.stages:
            if _unit(registry.stages[groups[-1][-1]]) == _unit(driver) and _unit(driver) != stage:
                groups[-1].append(stage)
                continue
        groups.append([stage])
    return groups


def _key_overlay(driver: Any, overlay: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """(overlay without model_config, model_config) as this driver's key sees them; ``key_overlay``
    on a driver narrows both to what the stage reads (the default is all of it)."""
    narrow = getattr(driver, 'key_overlay', None)
    if narrow is not None:
        base, model = narrow(overlay)
        return dict(base), dict(model)
    return {k: v for k, v in overlay.items() if k != 'model_config'}, dict(overlay.get('model_config') or {})


def _snapshot(run_dir: Path) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for path in run_dir.rglob('*'):
        if path.is_file():
            info = path.stat()
            out[path.relative_to(run_dir).as_posix()] = (info.st_size, info.st_mtime_ns)
    return out


def _changed(before: Mapping[str, tuple[int, int]], after: Mapping[str, tuple[int, int]]) -> list[str]:
    """Files a stage wrote: new or rewritten since ``before``, minus run-owned files, logs and locks."""
    out = []
    for relative, signature in after.items():
        name = relative.rsplit('/', 1)[-1]
        if relative in RUN_FILES or name.startswith('.') or name.endswith(('.lock', '.process.log')):
            continue
        if before.get(relative) != signature:
            out.append(relative)
    return sorted(out)


def _llm_rows(store: Store, run_id: str) -> list[dict[str, Any]]:
    from testing.pipeline_lab.store import read_jsonl

    return read_jsonl(store.llm_calls_path(run_id))


def _llm_count(store: Store, run_id: str) -> int:
    return len(_llm_rows(store, run_id))


def _llm_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    served = sum(1 for row in rows if row.get('cache_hit'))
    return {'llm_calls': len(rows), 'llm_upstream': len(rows) - served, 'llm_proxy_cache': served}


def _report(cache: str, *, seconds: float = 0.0, **extra: Any) -> dict[str, Any]:
    """One stage's row: ``cache`` is hit | miss (ran, stored) | off (ran, not cacheable) | skipped |
    failed | not_registered. LLM counts are calls made during the stage: ``llm_upstream`` went to the
    upstream, ``llm_proxy_cache`` were served by the proxy cache. A hit makes none and reports the
    ``saved_llm_calls`` the stored run made."""
    row: dict[str, Any] = {'cache': cache, 'seconds': seconds, 'llm_calls': 0, 'llm_upstream': 0, 'llm_proxy_cache': 0}
    row.update({k: v for k, v in extra.items() if v is not None})
    return row


def stage_report(selected: Sequence[str], reports: Mapping[str, Mapping[str, Any]], run: RunRecord) -> dict[str, Any]:
    """Run-level summary of the per-stage rows, plus printable lines (``table``)."""
    rows = {stage: dict(reports.get(stage) or {'cache': 'pending'}) for stage in selected}
    count = lambda name: sum(1 for row in rows.values() if row.get('cache') == name)  # noqa: E731
    total = {
        k: sum(int(row.get(k) or 0) for row in rows.values()) for k in ('llm_calls', 'llm_upstream', 'llm_proxy_cache')
    }
    ran = count('miss') + count('off')
    hits = count('hit')
    summary: dict[str, Any] = {
        'hits': hits,
        'ran': ran,
        'skipped': count('skipped'),
        'failed': count('failed'),
        'all_cached': bool(rows) and hits == len([r for r in rows.values() if r.get('cache') != 'not_registered']),
        **total,
        'saved_llm_calls': sum(int(row.get('saved_llm_calls') or 0) for row in rows.values()),
        'seconds': round(sum(float(row.get('seconds') or 0.0) for row in rows.values()), 3),
    }
    if summary['all_cached']:
        headline = f'stage cache: all {hits} stages served from the cache; nothing re-ran, 0 LLM calls'
    else:
        headline = (
            f'stage cache: {hits} hit, {ran} ran, {summary["skipped"]} skipped, {summary["failed"]} failed; '
            f'LLM calls {total["llm_calls"]} ({total["llm_upstream"]} upstream, {total["llm_proxy_cache"]} proxy cache)'
        )
    table = [headline, f'{"stage":<14}{"cache":<8}{"unit":<7}{"seconds":>9}{"llm":>6}{"upstr":>7}{"pcache":>8}']
    for stage, row in rows.items():
        unit = (run.stages.get(stage).extra.get('unit') if run.stages.get(stage) else None) or '-'
        table.append(
            f'{stage:<14}{row.get("cache", ""):<8}{unit:<7}{float(row.get("seconds") or 0):>9.3f}'
            f'{int(row.get("llm_calls") or 0):>6}{int(row.get("llm_upstream") or 0):>7}{int(row.get("llm_proxy_cache") or 0):>8}'
        )
    summary['line'] = headline
    summary['table'] = table
    return summary


def _code_state(worktree: Optional[worktrees.Worktree], in_place_repo: Optional[Path], run: RunRecord) -> Any:
    """The checked-out code, for code keys (None in tests that pass a bare tree hash)."""
    repo = worktree.path if worktree is not None else in_place_repo
    if repo is None:
        return None
    from testing.pipeline_lab.affected import CodeState

    try:
        return CodeState(Path(repo))
    except Exception as failure:  # noqa: BLE001 - fall back to the whole tree hash, and say so
        run.warnings.append(f'code keys fall back to the backend tree hash: {type(failure).__name__}')
        return None


def harness_identity() -> str:
    """sha256 over the executing lab package (sources and static files, no bytecode).

    A pinned ref runs this checkout's lab copied in by ``worktrees.vendor_lab``, so the product arm's code
    key alone would serve artifacts an older harness produced; every stage key carries this too.
    """
    import hashlib

    root = worktrees.harness_package_dir()
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


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
            run.warnings.append(
                'in-place run: backend/ has uncommitted changes; backend_tree names HEAD, stage keys include the edits'
            )
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
    artifact_digests: dict[str, str] = {}
    reports: dict[str, dict[str, Any]] = {}
    code = _code_state(worktree, in_place_repo, run)
    key_tree = code.tree_key() if code is not None else tree
    harness = harness_identity()
    exit_code, error = EXIT_OK, None
    walked = False
    try:
        for group in _groups(selected, registry):
            first = group[0]
            if first not in registry.stages:
                run.stages[first].status = StageState.NOT_REGISTERED.value
                run.warnings.append(f'stage driver not registered: {first} (skipped)')
                reports[first] = _report('not_registered')
                store.write_run(run)
                continue
            drivers = [registry.stages[stage] for stage in group]
            unit = _unit(drivers[0])
            members = [s for s in STAGES if s in registry.stages and _unit(registry.stages[s]) == unit]
            whole = list(group) == members
            if len(members) > 1 and not whole:
                run.warnings.append(f'unit {unit} ({", ".join(members)}) only partly selected: not cached')
            contexts = {
                stage: StageContext(
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
                for stage in group
            }
            for stage in group:
                run.stages[stage].status = StageState.RUNNING.value
                if len(members) > 1:
                    run.stages[stage].extra['unit'] = unit
            store.write_run(run)
            forced = forced_from is not None and max(stage_index(s) for s in group) >= forced_from
            before_start = forced_from is not None and not forced
            if forced and len(group) > 1 and stage_index(first) < forced_from:  # type: ignore[operator]
                run.warnings.append(
                    f'--from-stage {request.from_stage} is inside unit {unit} ({first}..{group[-1]}): '
                    f'the unit re-runs from {first}'
                )
            current = first
            group_started = time.monotonic()
            try:
                ctx0 = contexts[first]
                inputs = _stage_inputs(day, upstream)
                inputs.update({f'artifacts:{name}': digest for name, digest in artifact_digests.items()})
                inputs['pipeline'] = pipeline  # a classic entry is never served to a v3 run, or back
                inputs['harness'] = harness  # the lab code that executes, not only the product arm's
                if len(members) > 1:
                    inputs['unit'] = ','.join(group)
                for driver in drivers:
                    extra_inputs = getattr(driver, 'inputs', None)
                    if extra_inputs is not None:
                        prefix = 'driver:' if driver is drivers[0] else f'driver:{driver.stage}:'
                        inputs.update({f'{prefix}{k}': v for k, v in extra_inputs(ctx0).items()})
                if code is not None and any(getattr(d, 'ambient_env', False) for d in drivers):
                    inputs['ambient_env'] = code.ambient_env(group, overlay=env)
                key_overlay, key_model = _key_overlay(drivers[0], request.overlay)
                scoped = code is not None and all(getattr(d, 'scoped_code', False) for d in drivers)
                key = keys.stage_key(
                    first,
                    backend_tree=code.stage_key(group) if scoped else key_tree,  # type: ignore[union-attr]
                    inputs=inputs,
                    overlay=key_overlay,
                    model_config=key_model,
                    schema_version=max(int(getattr(d, 'schema_version', 1)) for d in drivers),
                )
                cacheable = whole and all(bool(getattr(d, 'cacheable', True)) for d in drivers) and not request.no_cache
                # refresh asks the upstream again, so it never takes a stored result (it still stores one)
                lookup = cacheable and not forced and request.llm_mode != 'refresh'
                entry = store.cache_get(first, key) if lookup else None
                if entry is not None and not store.cache_files_present(first, key, entry.get('artifacts') or []):
                    run.warnings.append(f'{first}: cache entry is missing stored artifacts (re-running)')
                    entry = None
                for stage in group:
                    run.stages[stage].extra['key'] = key
                if entry is None and before_start:
                    for stage in group:
                        run.stages[stage].status = StageState.SKIPPED.value
                        reports[stage] = _report('skipped')
                        run.warnings.append(f'{stage}: before --from-stage and not cached (skipped)')
                    continue
                if entry is not None:
                    store.cache_restore_files(first, key, store.run_dir(run_id), entry.get('artifacts') or [])
                    outputs = entry.get('outputs') or {first: entry.get('output') or {}}
                    saved = entry.get('llm') or {}
                    for stage, driver in zip(group, drivers):
                        current = stage
                        output = outputs.get(stage) or {}
                        restore = getattr(driver, 'restore', None)
                        if restore is not None:
                            restore(contexts[stage], output)
                        run.extra.update(contexts[stage].run_extra)
                        run.stages[stage].status = StageState.CACHED.value
                        run.stages[stage].cache_hits += 1
                        upstream[stage] = output
                        reports[stage] = _report(
                            'hit',
                            seconds=round(time.monotonic() - group_started, 3) if stage == first else 0.0,
                            saved_llm_calls=int((saved.get(stage) or {}).get('llm_calls') or 0),
                            cached_from=entry.get('run_id'),
                        )
                        run.timings[stage] = reports[stage]['seconds']
                    if entry.get('artifact_digest'):
                        artifact_digests[first] = entry['artifact_digest']
                    continue
                # Always: downstream keys need what this stage wrote even when its result is not stored.
                before = _snapshot(store.run_dir(run_id))
                outputs = {}
                calls_by_stage: dict[str, list[dict[str, Any]]] = {}
                for stage, driver in zip(group, drivers):
                    current = stage
                    ctx = contexts[stage]
                    ctx.upstream = dict(upstream)
                    started = time.monotonic()
                    calls_before = _llm_count(store, run_id)
                    try:
                        result = driver.run(ctx)
                        if not isinstance(result, StageResult):
                            raise TypeError(f'{stage} driver returned {type(result).__name__}, expected StageResult')
                    finally:
                        run.timings[stage] = round(time.monotonic() - started, 3)
                    rows = _llm_rows(store, run_id)[calls_before:]
                    attribute = getattr(driver, 'attribute_call', None)
                    for row in rows:
                        owner = attribute(row) if attribute is not None else None
                        calls_by_stage.setdefault(owner if owner in group else stage, []).append(row)
                    output = result.output
                    outputs[stage] = output
                    state = run.stages[stage]
                    state.status = StageState.COMPLETE.value
                    state.cache_hits += result.cache_hits
                    state.cache_misses += result.cache_misses
                    run.warnings.extend(f'{stage}: {w}' for w in result.warnings)
                    run.warnings.extend(f'{stage}: {w}' for w in ctx.warnings)
                    run.extra.update(ctx.run_extra)
                    upstream[stage] = output
                    if proxy is not None and proxy.cap_reached:
                        raise SpendCapReached('LLM proxy refused a call at the spend cap')
                llm = {stage: _llm_summary(calls_by_stage.get(stage) or []) for stage in group}
                for stage in group:
                    timings = outputs[stage].get('timings') if isinstance(outputs[stage], dict) else None
                    reports[stage] = _report(
                        'miss' if cacheable else 'off',
                        seconds=run.timings.get(stage, 0.0),
                        breakdown=timings if isinstance(timings, dict) else None,
                        **llm[stage],
                    )
                verdict = getattr(drivers[0], 'cache_ok', None)
                refusal = verdict(outputs) if verdict is not None and cacheable else None
                if refusal:
                    run.warnings.append(f'{first}: not stored in the stage cache ({refusal})')
                    for stage in group:
                        reports[stage]['cache'] = 'off'
                artifacts = _changed(before, _snapshot(store.run_dir(run_id)))
                # The artifacts' identity keys every later stage, whether or not this result is stored: a refused
                # (transient) or uncached result still feeds its files downstream, and its summary counts alone
                # cannot tell two different sets of transcripts apart.
                artifact_digests[first] = keys.hash_json(
                    {rel: keys.hash_file(store.run_dir(run_id) / rel) for rel in artifacts}
                )
                if cacheable and not refusal:
                    digests = store.cache_put_files(first, key, store.run_dir(run_id), artifacts)
                    digest = keys.hash_json(digests)
                    artifact_digests[first] = digest
                    store.cache_put(
                        first,
                        key,
                        {
                            'output': outputs[first],
                            'outputs': outputs,
                            'artifacts': artifacts,
                            'artifact_digest': digest,
                            'llm': llm,
                            'run_id': run_id,
                            'seconds': round(time.monotonic() - group_started, 3),
                        },
                    )
            except SpendCapReached as stop:
                run.stages[current].status = StageState.FAILED.value
                reports[current] = _report('failed', seconds=run.timings.get(current, 0.0))
                exit_code, error = EXIT_SPEND, f'spend stop in {current}: {stop}'
            except Exception as failure:  # noqa: BLE001 - recorded, then the run stops
                run.stages[current].status = StageState.FAILED.value
                reports[current] = _report('failed', seconds=run.timings.get(current, 0.0))
                exit_code, error = EXIT_ERROR, f'{current} failed: {type(failure).__name__}: {failure}'
                atomic_write_bytes(
                    store.run_dir(run_id) / 'errors.log', traceback.format_exc().encode('utf-8', errors='replace')
                )
            finally:
                for stage, report in reports.items():
                    run.stages[stage].extra['report'] = report
                run.extra['stage_report'] = stage_report(selected, reports, run)
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
        run.extra['stage_report'] = stage_report(selected, reports, run)
        store.write_run(run)
    return RunOutcome(run=run, exit_code=exit_code, error=error)
