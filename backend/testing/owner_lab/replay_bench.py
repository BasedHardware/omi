"""Paired A/B replay bench: pinned arms, interleaved repeats, a hard spend stop, offline reports.

This module is the feature-agnostic machinery. An *arm* pins a code ref (a git
checkout the runner verifies) plus an env overlay, and every run executes in its
own subprocess against its own tree, so arms can never share interpreter state.
A *feature adapter* plugs in through three calls: list bench cases, replay one
case, and fingerprint the first model request (zero-LLM parity across arms).

Costs are capped by a file-backed USD ledger: every request reserves its worst
case before it is sent, so an in-flight request is always charged and a crash
can never overspend the stop. Credentials enter only as a token FILE path
(``OWNER_LAB_GATEWAY_TOKEN_FILE``, mode 0600). Bench configs, selections and
results live outside Git; see README.md for the privacy rules.

Exit codes: 0 ok, 2 terminal error, 3 transport stop (retryable),
4 spend stop (terminal, resumable after a ledger review).
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

EXIT_OK = 0
EXIT_ERROR = 2
EXIT_TRANSPORT = 3
EXIT_SPEND = 4

TOKEN_FILE_ENV = 'OWNER_LAB_GATEWAY_TOKEN_FILE'
GATEWAY_URL_ENV = 'OWNER_LAB_GATEWAY_URL'
UID_ENV = 'OWNER_LAB_UID'
SNAPSHOT_ENV = 'OWNER_LAB_SNAPSHOT'
CASES_ENV = 'OWNER_LAB_CASES'
ARM_ENV = 'OWNER_LAB_ARM'
SELECTION_ENV = 'OWNER_LAB_SELECTION'

# A spend stop ends the bench; a transport drop may clear by itself (tunnel
# reconnect), so only the driver decides to retry it. Anything else is terminal.
STOP_EXIT = {'spend': EXIT_SPEND, 'transport': EXIT_TRANSPORT}
DRIVE_EXIT = {'complete': EXIT_OK, 'stopped': EXIT_SPEND, 'failed': EXIT_ERROR}


class ControlledStop(Exception):
    """A deliberate, resumable stop. ``kind`` picks the worker exit code."""

    def __init__(self, kind: str, detail: str = ''):
        super().__init__(f'{kind}: {detail}' if detail else kind)
        self.kind = kind


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, value: Any) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, default=str) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


@dataclass
class SpendLedger:
    """File-backed USD ledger: ``estimated`` spent, ``uncertain`` reserved in flight."""

    path: Path
    soft_stop_usd: float
    hard_stop_usd: float
    max_request_bytes: int = 2_000_000

    def load(self) -> dict[str, Any]:
        ledger = read_json(self.path, {'estimated_usd': 0.0, 'uncertain_usd': 0.0, 'requests': 0})
        return {
            'estimated_usd': float(ledger.get('estimated_usd') or 0.0),
            'uncertain_usd': float(ledger.get('uncertain_usd') or 0.0),
            'requests': int(ledger.get('requests') or 0),
        }

    @staticmethod
    def committed(ledger: Mapping[str, Any]) -> float:
        return ledger['estimated_usd'] + ledger['uncertain_usd']

    def reserve(self, usd: float) -> None:
        """Charge an in-flight request its worst case before anything is sent."""
        ledger = self.load()
        if self.committed(ledger) + usd > self.soft_stop_usd:
            raise ControlledStop('spend', 'reservation exceeds the soft stop')
        ledger['uncertain_usd'] += usd
        ledger['requests'] += 1
        write_json(self.path, ledger)

    def settle(self, reserved_usd: float, cost_usd: float) -> None:
        """Replace a reservation with the measured cost; the hard stop is absolute."""
        ledger = self.load()
        ledger['uncertain_usd'] = max(0.0, ledger['uncertain_usd'] - reserved_usd)
        ledger['estimated_usd'] += cost_usd
        write_json(self.path, ledger)
        if self.committed(ledger) >= self.hard_stop_usd:
            raise ControlledStop('spend', 'hard stop reached')


@dataclass
class GatewayTransport:
    """The one network door: a local LLM gateway, spend-guarded, reservation first."""

    url: str
    token_file: Path
    ledger: SpendLedger
    price_in_per_million: float = 0.10
    price_out_per_million: float = 0.60
    image_cushion_usd: float = 0.05
    billed_model_markers: Sequence[str] = ('gpt-6-luna',)
    timeout: float = 120.0
    opener: Any = None

    def __post_init__(self) -> None:
        if self.token_file.stat().st_mode & 0o077:
            raise ControlledStop('credential', 'token file must be mode 0600')
        self._token = self.token_file.read_text().strip()
        if not self._token:
            raise ControlledStop('credential', 'empty token file')

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args: Any, **kwargs: Any) -> None:
                raise ControlledStop('network', 'redirect refused')

        self._opener = self.opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def allowed_peer(self) -> tuple[str, int]:
        parsed = urllib.parse.urlsplit(self.url)
        return (parsed.hostname or '127.0.0.1', parsed.port or (443 if parsed.scheme == 'https' else 80))

    def complete(self, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body, ensure_ascii=False).encode()
        reserve = (
            len(payload) * self.price_in_per_million / 1e6
            + float(body.get('max_completion_tokens') or 6000) * self.price_out_per_million / 1e6
            + self.image_cushion_usd
        )
        if len(payload) > self.ledger.max_request_bytes:
            raise ControlledStop('input', 'request body over the byte cap')
        self.ledger.reserve(reserve)
        request = urllib.request.Request(
            self.url.rstrip('/') + '/v1/chat/completions',
            data=payload,
            headers={
                'Authorization': 'Bearer ' + self._token,
                'Content-Type': 'application/json',
                'X-Omi-Service-Caller': 'backend',
                'X-Omi-Usage-Feature': 'owner_lab',
            },
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            kind = 'transport' if error.code >= 500 else 'gateway'
            raise ControlledStop(kind, f'HTTP {error.code}') from None
        except ControlledStop:
            raise
        except Exception as error:  # noqa: BLE001 - any socket/decode failure is a transport drop
            raise ControlledStop('transport', type(error).__name__) from None
        usage = result.get('usage') or {}
        model = str(result.get('model') or '')
        if not any(marker in model for marker in self.billed_model_markers):
            raise ControlledStop('model', 'unexpected billed model; reservation retained')
        if not isinstance(usage.get('prompt_tokens'), int) or not isinstance(usage.get('completion_tokens'), int):
            raise ControlledStop('model', 'usage missing; reservation retained')
        prompt = usage['prompt_tokens']
        cached = min(prompt, (usage.get('prompt_tokens_details') or {}).get('cached_tokens') or 0)
        output = usage['completion_tokens']
        cost = (
            (prompt - cached) * self.price_in_per_million
            + cached * self.price_in_per_million / 10.0
            + output * self.price_out_per_million
        ) / 1e6
        self.ledger.settle(reserve, cost)
        return result


@contextmanager
def local_only_sockets(allowed: Sequence[tuple[str, int]]):
    """Deny every outbound connect except the listed (host, port) peers."""
    peers = {tuple(peer) for peer in allowed}
    connect = socket.socket.connect

    def guarded(sock: socket.socket, address: Any) -> Any:
        if not isinstance(address, tuple) or address[:2] not in peers:
            raise ControlledStop('network', 'non-gateway connect denied')
        return connect(sock, address)

    socket.socket.connect = guarded  # type: ignore[method-assign]
    try:
        yield
    finally:
        socket.socket.connect = connect  # type: ignore[method-assign]


@dataclass(frozen=True)
class Arm:
    """One pinned arm: a verified checkout plus an env overlay. The tree must sit at ``ref``."""

    name: str
    adapter: str
    tree: str
    ref: str
    env: Mapping[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {'name': self.name, 'adapter': self.adapter, 'tree': self.tree, 'ref': self.ref, 'env': dict(self.env)}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> 'Arm':
        return cls(
            name=str(data['name']),
            adapter=str(data['adapter']),
            tree=str(data['tree']),
            ref=str(data['ref']),
            env={str(k): str(v) for k, v in (data.get('env') or {}).items()},
        )


@dataclass(frozen=True)
class BenchConfig:
    arms: tuple[Arm, ...]
    repeats: int = 2
    soft_stop_usd: float = 2.80
    hard_stop_usd: float = 3.00
    max_request_bytes: int = 2_000_000
    results_path: str = 'runs.jsonl'
    ledger_path: str = 'spend.json'
    selection_path: str = 'selection.json'
    parity_path: str = 'parity.json'
    price_in_per_million: float = 0.10
    price_out_per_million: float = 0.60
    billed_model_markers: tuple[str, ...] = ('gpt-6-luna',)

    @classmethod
    def load(cls, path: Path) -> 'BenchConfig':
        raw = json.loads(path.read_text())
        config = cls(
            arms=tuple(Arm.from_json(arm) for arm in raw['arms']),
            repeats=int(raw.get('repeats') or 2),
            soft_stop_usd=float(raw.get('soft_stop_usd') or 2.80),
            hard_stop_usd=float(raw.get('hard_stop_usd') or max(3.0, float(raw.get('soft_stop_usd') or 2.80) + 0.2)),
            max_request_bytes=int(raw.get('max_request_bytes') or 2_000_000),
            results_path=str(raw.get('results_path') or 'runs.jsonl'),
            ledger_path=str(raw.get('ledger_path') or 'spend.json'),
            selection_path=str(raw.get('selection_path') or 'selection.json'),
            parity_path=str(raw.get('parity_path') or 'parity.json'),
            price_in_per_million=float(raw.get('price_in_per_million') or 0.10),
            price_out_per_million=float(raw.get('price_out_per_million') or 0.60),
            billed_model_markers=tuple(raw.get('billed_model_markers') or ('gpt-6-luna',)),
        )
        config.validate()
        return config

    def validate(self) -> None:
        names = [arm.name for arm in self.arms]
        if not names or len(set(names)) != len(names):
            raise SystemExit('config: arm names must be nonempty and unique')
        if not self.arms or any(not arm.ref or not arm.tree or not arm.adapter for arm in self.arms):
            raise SystemExit('config: every arm needs name, adapter, tree and a pinned ref')
        if self.repeats < 1:
            raise SystemExit('config: repeats must be >= 1')
        if self.hard_stop_usd < self.soft_stop_usd:
            raise SystemExit('config: hard stop below the soft stop')

    def resolve(self, base: Path) -> dict[str, Path]:
        return {
            'results': base / self.results_path,
            'ledger': base / self.ledger_path,
            'selection': base / self.selection_path,
            'parity': base / self.parity_path,
        }


class ReplayAdapter:
    """The feature contract the bench drives. Product code under test comes from the arm tree.

    ``run_case`` receives the spend-guarded transport (None in offline modes) and
    returns a metrics row without the arm/case/repeat stamps the runner adds.
    Optional hooks (``select``, ``qualify``) are called when present.
    """

    def case_ids(self) -> list[str]:
        raise NotImplementedError

    def run_case(self, case_id: str, transport: GatewayTransport | None) -> dict[str, Any]:
        raise NotImplementedError

    def first_request(self, case_id: str) -> Mapping[str, Any]:
        raise NotImplementedError


def load_adapter(spec: str) -> ReplayAdapter:
    module_path, _, attr = spec.partition(':')
    module = importlib.import_module(module_path)
    factory = getattr(module, attr or 'build_adapter')
    return factory()


def verify_arm_pin(arm: Arm) -> None:
    head = subprocess.check_output(['git', '-C', arm.tree, 'rev-parse', 'HEAD'], text=True).strip()
    if head != arm.ref:
        raise SystemExit(f'arm {arm.name}: tree HEAD {head[:12]} does not match the pinned ref {arm.ref[:12]}')


def interleave(cases: Sequence[str], arm_names: Sequence[str], repeats: int) -> list[tuple[str, str, int]]:
    """(arm, case, repeat) in an order that rotates arms per case and repeat.

    Consecutive runs never share an arm when more than one exists, so a provider
    or cache hiccup lands across arms instead of inside one.
    """
    order: list[tuple[str, str, int]] = []
    for repeat in range(repeats):
        for index, case_id in enumerate(cases):
            shift = (index + repeat) % len(arm_names)
            rotated = arm_names[shift:] + arm_names[:shift]
            order.extend((arm, case_id, repeat) for arm in rotated)
    return order


def completed_keys(results_path: Path) -> set[tuple[str, str, int]]:
    if not results_path.exists():
        return set()
    keys = set()
    for line in results_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        keys.add((str(row['arm']), str(row['id']), int(row['repeat'])))
    return keys


def pending_keys(plan: Sequence[tuple[str, str, int]], results_path: Path) -> list[tuple[str, str, int]]:
    """The plan minus what the results file already records; restarting never re-runs a done key."""
    done = completed_keys(results_path)
    return [key for key in plan if key not in done]


def drive_exit(state: str) -> int:
    return DRIVE_EXIT[state]


def append_row(results_path: Path, row: Mapping[str, Any]) -> None:
    # Run rows carry conversation ids: owner-only at creation, and a file
    # inherited with looser permissions tightens on resume rather than persisting.
    results_path.touch(0o600, exist_ok=True)
    results_path.chmod(0o600)
    with results_path.open('a') as stream:
        stream.write(json.dumps(row, default=str) + '\n')
        stream.flush()


def drive(
    plan: Sequence[tuple[str, str, int]],
    spawn: Callable[[tuple[str, str, int]], int],
    *,
    max_consecutive_failures: int = 3,
    retry_wait_seconds: float = 15.0,
    sleep: Callable[[float], None] = time.sleep,
    on_result: Callable[[tuple[str, str, int]], None] | None = None,
) -> tuple[str, str]:
    """Run the plan one worker at a time; transport stops retry, three in a row stop the bench."""
    failures = 0
    for key in plan:
        while True:
            code = spawn(key)
            if code == EXIT_OK:
                failures = 0
                if on_result is not None:
                    on_result(key)
                break
            if code == EXIT_TRANSPORT and failures + 1 < max_consecutive_failures:
                failures += 1
                print(f'RETRY {key[0]} consecutive_failures={failures}', flush=True)
                sleep(retry_wait_seconds)
                continue
            state = 'stopped' if code == EXIT_SPEND else 'failed'
            return state, f'exit {code} at {key[0]} (consecutive failures {failures + 1})'
    return 'complete', ''


def fingerprint(body: Mapping[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str).encode()
    return {
        'request_sha256': hashlib.sha256(encoded).hexdigest(),
        'request_bytes': len(encoded),
        'cache_key_sha256': hashlib.sha256(str(body.get('prompt_cache_key')).encode()).hexdigest(),
    }


def worker_env(arm: Arm) -> dict[str, str]:
    """The parent environment minus credential-shaped keys, plus the arm overlay.

    Callers must build this BEFORE replacing their own os.environ.
    """
    env = dict(os.environ)
    for key in list(env):
        if key in ('GOOGLE_APPLICATION_CREDENTIALS', 'SERVICE_ACCOUNT_JSON') or key.endswith('_SERVE_UID_SHA256S'):
            del env[key]
    env.update(arm.env)
    return env


def arm_backend_root(arm: Arm) -> Path:
    return Path(arm.tree) / 'backend'


def vendor_harness() -> Path:
    """A private copy of this harness package; product code resolves from the arm tree only.

    The copy holds ONLY ``testing/owner_lab`` — never a second ``backend`` — so
    ``utils``, ``models`` and ``database`` imports have exactly one source: the
    arm's pinned tree. Without this, a full harness backend first on ``sys.path``
    would make every arm measure the harness tree's code.
    """
    source = Path(__file__).resolve().parent
    vendor = Path(tempfile.mkdtemp(prefix='owner-lab-bench-'))
    shutil.copytree(source, vendor / 'testing' / 'owner_lab', ignore=shutil.ignore_patterns('__pycache__'))
    atexit.register(shutil.rmtree, vendor, True)
    return vendor


def worker(config_path: Path, arm_name: str, mode: str, case_id: str, repeat: int) -> int:
    config = BenchConfig.load(config_path)
    arm = next((arm for arm in config.arms if arm.name == arm_name), None)
    if arm is None:
        raise SystemExit(f'unknown arm {arm_name}')
    verify_arm_pin(arm)
    env = worker_env(arm)  # snapshot the parent environment before replacing it
    os.environ.clear()
    os.environ.update(env)
    os.environ[ARM_ENV] = arm.name
    sys.path[:0] = [str(vendor_harness()), str(arm_backend_root(arm))]
    base = config_path.parent
    paths = config.resolve(base)
    os.environ[SELECTION_ENV] = str(paths['selection'])
    adapter = load_adapter(arm.adapter)
    ledger = SpendLedger(
        path=paths['ledger'],
        soft_stop_usd=config.soft_stop_usd,
        hard_stop_usd=config.hard_stop_usd,
        max_request_bytes=config.max_request_bytes,
    )
    if mode == 'parity':
        records = []
        for case in adapter.case_ids():
            body = adapter.first_request(case)
            records.append({'id': case, **fingerprint(body)})
        write_json(base / f'parity-{arm.name}.json', records)
        print(f'PARITY arm={arm.name} cases={len(records)} model_requests=0', flush=True)
        return EXIT_OK
    if mode == 'select':
        if not hasattr(adapter, 'select'):
            raise SystemExit(f'adapter {arm.adapter} has no select hook')
        adapter.select(paths['selection'])
        print(f'SELECT arm={arm.name} model_requests=0', flush=True)
        return EXIT_OK
    if mode == 'qualify':
        if not hasattr(adapter, 'qualify'):
            raise SystemExit(f'adapter {arm.adapter} has no qualify hook')
        adapter.qualify()
        print(f'QUALIFIED arm={arm.name} model_requests=0', flush=True)
        return EXIT_OK
    transport = None
    if GATEWAY_URL_ENV in os.environ and TOKEN_FILE_ENV in os.environ:
        transport = GatewayTransport(
            url=os.environ[GATEWAY_URL_ENV],
            token_file=Path(os.environ[TOKEN_FILE_ENV]),
            ledger=ledger,
            price_in_per_million=config.price_in_per_million,
            price_out_per_million=config.price_out_per_million,
            billed_model_markers=config.billed_model_markers,
        )
    try:
        with local_only_sockets([transport.allowed_peer()] if transport else ()):
            row = adapter.run_case(case_id, transport)
    except ControlledStop as stop:
        print(f'STOP {stop}', flush=True)
        return STOP_EXIT.get(stop.kind, EXIT_ERROR)
    if row is None:
        raise SystemExit(f'adapter returned no row for {case_id}')
    row.update(arm=arm.name, id=case_id, repeat=repeat)
    append_row(paths['results'], row)
    ledger_view = ledger.load()
    print(
        f"RUN arm={arm.name} id={case_id} rep={repeat} stop={row.get('stop')} "
        f"forced={row.get('forced')} lookups={row.get('lookups')} cost={row.get('cost')}",
        flush=True,
    )
    print(
        f"SPEND estimated_usd={ledger_view['estimated_usd']:.4f} "
        f"uncertain_usd={ledger_view['uncertain_usd']:.4f} requests={ledger_view['requests']}",
        flush=True,
    )
    return EXIT_OK


def worker_command(config_path: Path, arm_name: str, mode: str, case_id: str, repeat: int) -> list[str]:
    return [
        sys.executable,
        '-I',
        str(Path(__file__).resolve()),
        '--config',
        str(config_path),
        '--worker',
        mode,
        '--arm',
        arm_name,
        '--case',
        case_id,
        '--repeat',
        str(repeat),
    ]


def run_bench(config_path: Path) -> int:
    config = BenchConfig.load(config_path)
    for arm in config.arms:
        verify_arm_pin(arm)
    base = config_path.parent
    paths = config.resolve(base)
    selection = read_json(paths['selection'], {})
    if not selection.get('ids'):
        raise SystemExit('no selection; run the select mode first')
    arm_names = [arm.name for arm in config.arms]
    plan = interleave(selection['ids'], arm_names, config.repeats)
    pending = pending_keys(plan, paths['results'])
    print(f'PLAN runs={len(plan)} pending={len(pending)} arms={arm_names} repeats={config.repeats}', flush=True)

    def spawn(key: tuple[str, str, int]) -> int:
        arm_name, case_id, repeat = key
        return subprocess.call(worker_command(config_path, arm_name, 'run', case_id, repeat))

    state, detail = drive(pending, spawn)
    print(f'BENCH {state.upper()} {detail}'.rstrip(), flush=True)
    return drive_exit(state)


def compare_parity(fingerprints: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Cases whose first-request fingerprint differs across arms (first arm is the reference)."""
    names = list(fingerprints)
    mismatched: list[dict[str, Any]] = []
    for row in fingerprints[names[0]]:
        for other in names[1:]:
            candidate = next((item for item in fingerprints[other] if item['id'] == row['id']), None)
            if candidate != row:
                mismatched.append({'id': row['id'], 'arms': [names[0], other]})
    return mismatched


def run_parity(config_path: Path) -> int:
    config = BenchConfig.load(config_path)
    base = config_path.parent
    paths = config.resolve(base)
    selection = read_json(paths['selection'], {})
    if not selection.get('ids'):
        raise SystemExit('no selection; run the select mode first')
    fingerprints: dict[str, list[dict[str, Any]]] = {}
    for arm in config.arms:
        code = subprocess.call(worker_command(config_path, arm.name, 'parity', selection['ids'][0], 0))
        if code:
            return code
        fingerprints[arm.name] = read_json(base / f'parity-{arm.name}.json', [])
    mismatched = compare_parity(fingerprints)
    result = {
        'model_requests': 0,
        'conversations': len(fingerprints[config.arms[0].name]),
        'mismatched': mismatched,
        'identical_first_requests': not mismatched,
    }
    write_json(paths['parity'], result)
    print(json.dumps({'identical_first_requests': result['identical_first_requests'], 'mismatched': len(mismatched)}))
    return EXIT_OK if not mismatched else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--config', required=True, help='bench config JSON (lives outside Git)')
    parser.add_argument('--worker', choices=('run', 'parity', 'select', 'qualify'), help='internal: one job')
    parser.add_argument('--arm')
    parser.add_argument('--case')
    parser.add_argument('--repeat', type=int, default=0)
    parser.add_argument('--mode', choices=('run', 'parity', 'select', 'qualify'), default='run')
    args = parser.parse_args(argv)
    config_path = Path(args.config).resolve()
    if args.worker:
        return worker(config_path, args.arm or '', args.worker, args.case or '', args.repeat)
    if args.mode == 'run':
        return run_bench(config_path)
    if args.mode == 'parity':
        return run_parity(config_path)
    config = BenchConfig.load(config_path)
    arm = config.arms[0]
    return subprocess.call(worker_command(config_path, arm.name, args.mode, '', 0))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ControlledStop as stop:
        print(f'STOP {stop}', flush=True)
        raise SystemExit(STOP_EXIT.get(stop.kind, EXIT_ERROR))
