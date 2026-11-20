"""Pipeline-lab command line (DESIGN "CLI"). Run from ``backend/``::

    python -m testing.pipeline_lab <command> [--json]

Every command accepts ``--json`` (machine output on stdout). Exit codes: 0 ok,
2 refusal or error, 3 transport stop, 4 spend stop. Commands whose engine belongs
to another lane (``corpus add-day``, ``record-stt``, ``serve``) dispatch to the
registered tool and fail with "tool not registered" until that lane plugs in.
Heavy commands (``run``, ``record-stt``) are wrapped by the caller in ``omi-heavy``;
``serve`` and ``llm-proxy`` are not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from testing.pipeline_lab import orchestrator, worktrees
from testing.pipeline_lab.contracts import ITEM_KINDS, MARKS, STAGES, Verdict, utc_iso
from testing.pipeline_lab.ledger import DEFAULT_BUDGET_USD, SpendLedger
from testing.pipeline_lab.registry import DriverNotRegistered, Registry, ToolContext, load_plugins
from testing.pipeline_lab.store import Store, StoreRefused, new_verdict_id


class CliError(Exception):
    def __init__(self, message: str, code: int = orchestrator.EXIT_ERROR):
        super().__init__(message)
        self.code = code


def _common() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument('--json', action='store_true', default=argparse.SUPPRESS, help='JSON on stdout')
    return parent


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = argparse.ArgumentParser(prog='python -m testing.pipeline_lab', description=__doc__.splitlines()[0])
    parser.add_argument('--root', help='run store (default $OMI_PIPELINE_LAB_ROOT)')
    parser.add_argument('--verdicts', help='verdict root (default $OMI_PIPELINE_LAB_VERDICTS)')
    parser.add_argument('--json', action='store_true', default=False, help='JSON on stdout')
    sub = parser.add_subparsers(dest='command', required=True)

    corpus = sub.add_parser('corpus', parents=[common], help='corpus days')
    corpus_sub = corpus.add_subparsers(dest='corpus_command', required=True)
    corpus_sub.add_parser('list', parents=[common], help='list corpus days')
    show_day = corpus_sub.add_parser('show', parents=[common], help='one corpus day')
    show_day.add_argument('day_id')
    corpus_sub.add_parser('add-day', parents=[common], help='build a corpus day (ingest/chain lanes)')

    sub.add_parser('record-stt', parents=[common], help='record STT cassettes (ingest lane)')

    run = sub.add_parser('run', parents=[common], help='replay a day at a ref')
    run.add_argument('--day', required=True)
    run.add_argument('--ref', required=True, help='branch, tag or commit to pin')
    run.add_argument(
        '--overlay', help='overlay JSON: {"name", "env":{}, "model_config":{}, "serving":{}, "gates":{}, "strict"}'
    )
    run.add_argument('--from-stage', choices=STAGES)
    run.add_argument('--stages', help='comma-separated subset of stages')
    run.add_argument('--budget-usd', type=float, default=DEFAULT_BUDGET_USD)
    run.add_argument('--repo', help='git repo to resolve the ref in (default: this checkout)')
    run.add_argument('--tree', help='use this existing checkout (must sit clean at the ref)')
    run.add_argument(
        '--in-place',
        action='store_true',
        help='run the backend of this checkout as is (unpinned; dirty trees are recorded as a warning)',
    )
    run.add_argument('--allow-lock-mismatch', action='store_true', help='warn instead of failing on lock drift')
    run.add_argument(
        '--engine',
        choices=('product', 'fake'),
        default='product',
        help='chain engine: product (real backend on the local stack) or fake (hermetic plumbing check)',
    )
    run.add_argument('--llm-upstream', help='LLM gateway URL the lab proxy forwards to')
    run.add_argument('--llm-mode', choices=('record', 'replay', 'refresh'), default='record')
    run.add_argument('--llm-prices', help='price table JSON file (USD per million tokens)')
    run.add_argument('--allow-missing', action='store_true', help='skip stages without a driver instead of failing')
    run.add_argument('--no-cache', action='store_true', help='ignore the stage cache')

    runs = sub.add_parser('runs', parents=[common], help='list runs')
    runs.add_argument('--day')

    show = sub.add_parser('show', parents=[common], help='show a run')
    show.add_argument('run_id')
    show.add_argument('--conversation', help='print one conversation record')
    show.add_argument('--calls', action='store_true', help='include the LLM call log')

    serve = sub.add_parser('serve', parents=[common], help='inspector web server (inspector lane)')
    serve.add_argument('--port', type=int)

    verdicts = sub.add_parser('verdicts', parents=[common], help='verdict marks')
    verdict_sub = verdicts.add_subparsers(dest='verdicts_command', required=True)
    for name in ('list', 'export'):
        command = verdict_sub.add_parser(name, parents=[common])
        command.add_argument('--run')
        command.add_argument('--day')
        command.add_argument('--kind', choices=ITEM_KINDS)
        command.add_argument('--mark', choices=MARKS)
        command.add_argument('--latest', action='store_true', help='newest mark per item only')
        if name == 'export':
            command.add_argument('--out', help='write here instead of stdout (outside git)')
            command.add_argument('--format', choices=('jsonl', 'json'), default='jsonl')
    add = verdict_sub.add_parser('add', parents=[common], help='record a mark (headless)')
    add.add_argument('--run', required=True)
    add.add_argument('--conversation')
    add.add_argument('--kind', required=True, choices=ITEM_KINDS)
    add.add_argument('--key', required=True)
    add.add_argument('--mark', required=True, choices=MARKS, help='clear withdraws an earlier mark')
    add.add_argument('--note', default='')

    sub.add_parser('sample-run', parents=[common], help='write a synthetic day + run')

    worktree = sub.add_parser('worktree', parents=[common], help='pinned per-ref worktrees')
    worktree_sub = worktree.add_subparsers(dest='worktree_command', required=True)
    for name in ('ensure', 'tree-hash'):
        command = worktree_sub.add_parser(name, parents=[common])
        command.add_argument('ref')
        command.add_argument('--repo')

    proxy = sub.add_parser('llm-proxy', parents=[common], help='run the LLM record/replay proxy in the foreground')
    proxy.add_argument('--run', required=True, help='run id whose ledger and call log to use')
    proxy.add_argument('--upstream', required=True)
    proxy.add_argument('--port', type=int, default=0)
    proxy.add_argument('--mode', choices=('record', 'replay', 'refresh'), default='record')
    proxy.add_argument('--prices', help='price table JSON file')
    proxy.add_argument('--budget-usd', type=float, help='defaults to the run budget')

    overlay = sub.add_parser('overlay', parents=[common], help='build run overlays')
    overlay_sub = overlay.add_subparsers(dest='overlay_command', required=True)
    from_env = overlay_sub.add_parser(
        'from-runtime-env', parents=[common], help="production flags from the ref's deploy/runtime_env.yaml"
    )
    from_env.add_argument('--runtime-env', help='runtime_env.yaml (default: backend/deploy/runtime_env.yaml here)')
    from_env.add_argument('--environment', default='prod')
    from_env.add_argument(
        '--service',
        default='backend-sync',
        help='gke or cloud_run service whose env to use (backend-sync runs the v3 reconcile and notes)',
    )
    from_env.add_argument(
        '--owner-uid-file',
        help='0600 file holding the owner uid, to resolve cohorts and uid allow-lists (never written)',
    )
    from_env.add_argument(
        '--live-env',
        help='filtered served env (overlay live-env output): adds the ops-file and live-only values production runs with',
    )
    from_env.add_argument('--out', help='write the overlay here (outside git) instead of stdout')
    live = overlay_sub.add_parser(
        'live-env',
        parents=[common],
        help='filter `gcloud run services describe --format=json` (stdin) to non-secret plain env, for --live-env',
    )
    live.add_argument('--out', required=True, help='write here (outside git)')
    live.add_argument('--owner-uid-file', required=True, help='0600 file holding the owner uid (scrubs uid lists)')

    sub.add_parser('stages', parents=[common], help='stages in order and their registered drivers')
    sub.add_parser('doctor', parents=[common], help='roots, permissions and plugins')
    return parser


def default_repo() -> Path:
    here = Path(__file__).resolve().parent
    top = worktrees.git(here, 'rev-parse', '--show-toplevel')
    return Path(top)


def _read_json_file(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    data = json.loads(Path(path).expanduser().read_text())
    if not isinstance(data, dict):
        raise CliError(f'{path}: expected a JSON object')
    return data


def _tool(registry: Registry, name: str, store: Store, args: argparse.Namespace, as_json: bool) -> Any:
    tool = registry.tool(name)
    return tool(ToolContext(store=store, args=args, argv=list(getattr(args, 'rest', []) or []), as_json=as_json))


def dispatch(args: argparse.Namespace, store: Store, registry: Registry, as_json: bool) -> tuple[Any, int]:
    command = args.command
    if command == 'corpus':
        if args.corpus_command == 'list':
            return [day.to_json() for day in store.list_days()], 0
        if args.corpus_command == 'show':
            day = store.read_day(args.day_id)
            return {
                'day': day.to_json(),
                'baseline_conversations': len(store.read_baseline(day.day_id, 'conversations.jsonl')),
                'audio_files': len(store.read_audio_index(day.day_id)),
            }, 0
        return _tool(registry, 'corpus-add-day', store, args, as_json), 0
    if command == 'record-stt':
        return _tool(registry, 'record-stt', store, args, as_json), 0
    if command == 'serve':
        return _tool(registry, 'serve', store, args, as_json), 0
    if command == 'sample-run':
        if 'sample-run' in registry.tools:
            return _tool(registry, 'sample-run', store, args, as_json), 0
        from testing.pipeline_lab.sample import write_sample

        return write_sample(store), 0
    if command == 'run':
        return _run(args, store, registry)
    if command == 'runs':
        return [_run_summary(run) for run in store.list_runs(args.day)], 0
    if command == 'show':
        return _show(args, store), 0
    if command == 'verdicts':
        return _verdicts(args, store)
    if command == 'worktree':
        repo = Path(args.repo) if args.repo else default_repo()
        if args.worktree_command == 'tree-hash':
            return {
                'ref': args.ref,
                'sha': worktrees.resolve_ref(repo, args.ref),
                'backend_tree': worktrees.tree_hash(repo, args.ref),
            }, 0
        return worktrees.ensure_worktree(repo, args.ref).to_json(), 0
    if command == 'llm-proxy':
        return _llm_proxy(args, store), 0
    if command == 'overlay':
        if args.overlay_command == 'live-env':
            return _overlay_live_env(args), 0
        return _overlay_from_runtime_env(args), 0
    if command == 'stages':
        return registry.describe(), 0
    if command == 'doctor':
        return {
            'root': str(store.root),
            'verdicts': str(store.verdicts_root),
            'runs': len(store.list_runs()),
            'days': len(store.list_days()),
            'python': sys.version.split()[0],
            **registry.describe(),
        }, 0
    raise CliError(f'unknown command {command}')


def _run_summary(run) -> dict[str, Any]:
    return {
        'run_id': run.run_id,
        'day_id': run.day_id,
        'ref': run.ref,
        'status': run.status,
        'started_at': run.started_at,
        'finished_at': run.finished_at,
        'spend_usd': run.spend_usd,
        'budget_usd': run.budget_usd,
    }


def _run(args: argparse.Namespace, store: Store, registry: Registry) -> tuple[Any, int]:
    overlay = _read_json_file(args.overlay)
    request = orchestrator.RunRequest(
        day_id=args.day,
        ref=args.ref,
        overlay=overlay,
        from_stage=args.from_stage,
        stages=[s.strip() for s in args.stages.split(',') if s.strip()] if args.stages else None,
        budget_usd=args.budget_usd,
        allow_missing=args.allow_missing,
        no_cache=args.no_cache,
        llm_upstream=args.llm_upstream,
        llm_mode=args.llm_mode,
        llm_prices=_read_json_file(args.llm_prices) or None,
        allow_lock_mismatch=args.allow_lock_mismatch,
        engine=args.engine,
    )
    repo = Path(args.repo) if args.repo else default_repo()
    worktree = None
    if args.in_place:
        if args.tree:
            raise CliError('--in-place and --tree are exclusive')
        request.commit = worktrees.resolve_ref(repo, 'HEAD')
        outcome = orchestrator.run_pipeline(
            store, request, registry, backend_tree=worktrees.tree_hash(repo, 'HEAD'), in_place_repo=repo
        )
        return {**outcome.run.to_json(), 'error': outcome.error}, outcome.exit_code
    if args.tree:
        worktree = worktrees.verify_worktree(Path(args.tree), worktrees.resolve_ref(repo, args.ref))
    outcome = orchestrator.run_pipeline(store, request, registry, worktree=worktree, repo=repo)
    body = {**outcome.run.to_json(), 'error': outcome.error}
    return body, outcome.exit_code


def _show(args: argparse.Namespace, store: Store) -> Any:
    run = store.read_run(args.run_id)
    if args.conversation:
        return store.read_conversation(run.run_id, args.conversation).to_json()
    conversations = store.list_conversations(run.run_id)
    calls = store.read_llm_calls(run.run_id)
    body: dict[str, Any] = {
        'run': run.to_json(),
        'conversations': {
            'total': len(conversations),
            'discarded': sum(1 for c in conversations if c.discarded),
            'action_items': sum(len(c.action_items) for c in conversations),
            'memories': sum(len(c.memories) for c in conversations),
            'notifications': sum(len(c.notifications) for c in conversations),
        },
        'llm_calls': {
            'total': len(calls),
            'cache_hits': sum(1 for c in calls if c.cache_hit),
            'usd': round(sum(c.usd for c in calls), 6),
        },
        'ledger': SpendLedger(store.ledger_path(run.run_id), budget_usd=run.budget_usd).snapshot(),
        'day': None,
    }
    run_day = store.read_run_day(run.run_id)
    if run_day is not None:
        body['day'] = run_day.to_json()
    if args.calls:
        body['calls'] = [call.to_json() for call in calls]
    return body


def _verdicts(args: argparse.Namespace, store: Store) -> tuple[Any, int]:
    if args.verdicts_command == 'add':
        run = store.read_run(args.run)
        snapshot = None
        if args.conversation:
            snapshot = {'conversation_id': args.conversation}
        verdict = Verdict(
            id=new_verdict_id(),
            at=utc_iso(),
            run_id=run.run_id,
            day_id=run.day_id,
            ref=run.ref,
            conversation_id=args.conversation,
            item_kind=args.kind,
            item_key=args.key,
            mark=args.mark,
            note=args.note,
            item_snapshot=snapshot,
        )
        return store.append_verdict(verdict).to_json(), 0
    rows = store.read_verdicts(
        run_id=args.run, day_id=args.day, item_kind=args.kind, mark=args.mark, latest=args.latest
    )
    payload = [row.to_json() for row in rows]
    if args.verdicts_command == 'export':
        text = (
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
            if args.format == 'json'
            else ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in payload)
        )
        if args.out:
            out = Path(args.out).expanduser().resolve()
            if any((parent / '.git').exists() for parent in (out.parent, *out.parent.parents)):
                raise CliError('verdict exports must be written outside every git worktree')
            from testing.pipeline_lab.store import atomic_write_bytes

            atomic_write_bytes(out, text.encode('utf-8'))
            return {'exported': len(payload), 'out': str(out)}, 0
        return _Raw(text), 0
    return payload, 0


def _outside_git(out: Path) -> Path:
    out = out.expanduser().resolve()
    if any((parent / '.git').exists() for parent in (out.parent, *out.parent.parents)):
        raise CliError('overlays are written outside every git worktree')
    return out


def _overlay_live_env(args: argparse.Namespace) -> Any:
    import json
    import sys

    from testing.pipeline_lab.stack.runtime_env import filter_live_env
    from testing.pipeline_lab.store import atomic_write_json

    filtered = filter_live_env(json.loads(sys.stdin.read()), read_private_value(Path(args.owner_uid_file)))
    out = _outside_git(Path(args.out))
    atomic_write_json(out, filtered)
    return {'out': str(out), **{k: v for k, v in filtered.items() if k != 'env'}, 'kept': len(filtered['env'])}


def read_private_value(path: Path) -> str:
    """The stripped contents of an owner-only regular file (no link, mode 0600 or tighter)."""
    import os
    import stat

    try:
        info = os.lstat(path)
    except OSError:
        raise CliError('private file not found') from None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise CliError('private file must be a regular file owned by you with mode 0600')
    value = path.read_text(encoding='utf-8').strip()
    if not value:
        raise CliError('private file is empty')
    return value


def _overlay_from_runtime_env(args: argparse.Namespace) -> Any:
    import os

    from testing.pipeline_lab.stack.runtime_env import overlay_from_runtime_env

    path = (
        Path(args.runtime_env)
        if args.runtime_env
        else Path(__file__).resolve().parents[2] / 'deploy' / 'runtime_env.yaml'
    )
    owner_uid = None  # from a 0600 file only, never the environment
    if args.owner_uid_file:
        owner_uid = read_private_value(Path(args.owner_uid_file))
    live_env = None
    if args.live_env:
        import json

        live_env = json.loads(Path(args.live_env).read_text(encoding='utf-8'))
    overlay, report = overlay_from_runtime_env(
        path, environment=args.environment, service=args.service, owner_uid=owner_uid, live_env=live_env
    )
    report.pop('dropped_names', None)
    report.pop('live_names', None)
    if args.out:
        out = Path(args.out).expanduser().resolve()
        if any((parent / '.git').exists() for parent in (out.parent, *out.parent.parents)):
            raise CliError('overlays are written outside every git worktree')
        from testing.pipeline_lab.store import atomic_write_json

        atomic_write_json(out, overlay)
        return {'out': str(out), **report}
    return {'overlay': overlay, 'report': report}


def _llm_proxy(args: argparse.Namespace, store: Store) -> Any:
    from testing.pipeline_lab.llm_proxy.server import LlmProxy, ProxyConfig
    from testing.pipeline_lab.llm_proxy.wire import PriceTable

    run = store.read_run(args.run)
    ledger = SpendLedger(store.ledger_path(run.run_id), budget_usd=args.budget_usd or run.budget_usd)
    proxy = LlmProxy(
        ProxyConfig(
            upstream=args.upstream,
            mode=args.mode,
            run_id=run.run_id,
            prices=PriceTable.from_json(_read_json_file(args.prices)),
        ),
        store=store,
        ledger=ledger,
        port=args.port,
    )

    def ready(url: str) -> None:
        print(json.dumps({'listening': url, 'run_id': run.run_id, 'mode': args.mode}), flush=True)

    try:
        proxy.serve_forever(on_ready=ready)
    except KeyboardInterrupt:
        pass
    return {'stopped': True, 'counters': proxy.counters, 'ledger': ledger.snapshot()}


class _Raw(str):
    """Already-formatted output (verdict export) printed verbatim."""


def _emit(value: Any, as_json: bool) -> None:
    if isinstance(value, _Raw):
        sys.stdout.write(value)
        return
    if as_json:
        print(json.dumps(value, ensure_ascii=False, default=str))
        return
    if isinstance(value, list):
        for row in value:
            print(json.dumps(row, ensure_ascii=False, default=str))
        return
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def main(argv: Optional[Sequence[str]] = None, *, registry: Optional[Registry] = None) -> int:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    # Engines owned by other lanes take their own flags; core passes them through untouched.
    passthrough = args.command in ('record-stt', 'serve', 'sample-run') or (
        args.command == 'corpus' and args.corpus_command == 'add-day'
    )
    if unknown and not passthrough:
        parser.error('unrecognized arguments: ' + ' '.join(unknown))
    args.rest = unknown
    as_json = bool(getattr(args, 'json', False))
    try:
        store = Store.open(Path(args.root) if args.root else None, Path(args.verdicts) if args.verdicts else None)
        if registry is None:
            registry = load_plugins(Registry())
        value, code = dispatch(args, store, registry, as_json)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        _emit(value, as_json)
        return code
    except (
        CliError,
        DriverNotRegistered,
        StoreRefused,
        FileNotFoundError,
        worktrees.WorktreeError,
        ValueError,
    ) as error:
        code = error.code if isinstance(error, CliError) else orchestrator.EXIT_ERROR
        message = str(error)
        if as_json:
            print(json.dumps({'error': message, 'kind': type(error).__name__}))
        else:
            print(f'error: {message}', file=sys.stderr)
        return code
    except subprocess.TimeoutExpired:
        print(json.dumps({'error': 'subprocess timeout'}) if as_json else 'error: subprocess timeout', file=sys.stderr)
        return orchestrator.EXIT_TRANSPORT
