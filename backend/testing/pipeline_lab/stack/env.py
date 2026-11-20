"""The persistent lab environment: one context manager the chain and day drivers run in.

Differences from ``testing/replay_harness/env.py`` (deliberate):
- persistent: writes go to the dev-up emulator project and are never deleted on exit;
- peers: Firestore + Auth emulators, real local Redis and Typesense and the lab LLM
  proxy are allowed (``network.NetworkPolicy``); everything else is refused;
- identity: the synthetic uid ``local-dev-user`` (DESIGN L4);
- overlay: explicit env, serve-mode pins and gate pins, logged to ``decisions.jsonl``.

Use ``install_product=False`` to get only the env/network layer (unit tests, tools
that must not import product modules).
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Iterator, Sequence
from unittest.mock import patch

from testing.pipeline_lab.stack.clock import LabClock, installed_clock
from testing.pipeline_lab.stack.config import LabStackConfig
from testing.pipeline_lab.stack.network import NetworkPolicy, guarded_network
from testing.pipeline_lab.stack.overlay import (
    DecisionLog,
    Overlay,
    install_gate_pins,
    resolve_pins,
    trace_serving_for,
)
from testing.pipeline_lab.stack.patching import replace_everywhere

INHERITED_ENV = ('PATH', 'TMPDIR', 'HOME', 'SYSTEMROOT', 'LANG', 'LC_ALL')

# When the local Typesense is not listening, every product index write waits out the client's
# retries (seconds per conversation). The product's own kill switch turns the dual-write off;
# search reads fail open as they would in an outage. Recorded as decision ``typesense_unavailable``.
TYPESENSE_DOWN_ENV = {'TYPESENSE_CONVERSATION_INDEX_WRITES': 'off', 'TYPESENSE_CONNECTION_TIMEOUT_SECONDS': '1'}


def peer_listening(peer: tuple[str, int], *, timeout: float = 0.5) -> bool:
    import socket

    try:
        with socket.create_connection(peer, timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class LabEnvironment:
    config: LabStackConfig
    overlay: Overlay
    decisions: DecisionLog
    network: NetworkPolicy
    clock: LabClock | None
    stack: ExitStack
    run_dir: Path | None = None
    firestore: Any = None
    redis: Any = None
    storage: Any = None
    settings: dict[str, str] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return self.config.uid


def compose_settings(
    config: LabStackConfig, overlay: Overlay, *, inherit: Sequence[str] = INHERITED_ENV
) -> dict[str, str]:
    """The full process env: a cleared base, the stack peers, then the overlay.

    The overlay may not rebind a stack peer (emulator hosts, proxy URL, storage root):
    those define where data goes and stay owned by the stack config.
    """
    settings = {name: os.environ[name] for name in inherit if name in os.environ}
    peers = config.product_env()
    settings.update(peers)
    rendered = overlay.render_env(config.uid)
    clashes = sorted(name for name in rendered if name in peers and rendered[name] != peers[name])
    if clashes:
        raise ValueError(f'overlay may not rebind stack settings: {clashes}')
    settings.update(rendered)
    return settings


def _emulator_firestore(config: LabStackConfig) -> Any:
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    return firestore.Client(project=config.project_id, credentials=AnonymousCredentials())


def _install_firestore(stack: ExitStack, client: Any) -> None:
    from database import _client

    stack.enter_context(patch.object(_client, 'get_firestore_client', lambda: client))
    for name in ('get_customer_firestore_client', 'get_data_plane_firestore_client'):
        if hasattr(_client, name):
            stack.enter_context(patch.object(_client, name, lambda: client))
    for attribute in ('_firestore_client', '_customer_firestore_client', '_data_plane_firestore_client'):
        if hasattr(_client, attribute):
            stack.enter_context(patch.object(_client, attribute, client))


def _install_redis(stack: ExitStack, client: Any) -> None:
    from database import redis_db

    original = redis_db.r
    stack.enter_context(patch.object(redis_db, 'r', client))
    replace_everywhere(stack, original, client)


def _install_storage(stack: ExitStack, root: Path) -> Any:
    from utils.other import local_storage, storage as product_storage

    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    client = local_storage.LocalStorageClient(root)
    stack.enter_context(patch.object(product_storage, '_get_storage_client', lambda: client))
    stack.enter_context(patch.object(local_storage, 'create_storage_client', lambda: client))
    return client


def _refuse(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError('pipeline lab refuses ambient cloud credentials')


@contextmanager
def lab_environment(
    config: LabStackConfig | None = None,
    overlay: Overlay | None = None,
    *,
    run_dir: Path | None = None,
    clock: LabClock | None = None,
    firestore_client: Any = None,
    redis_client: Any = None,
    install_product: bool = True,
    network_policy: NetworkPolicy | None = None,
    preimport: Sequence[str] = (),
) -> Iterator[LabEnvironment]:
    """``preimport``: product modules to import under the lab env *before* any patching,
    so their ``from x import f`` bindings are swapped (and restored) with everything else.
    Run the lab in a fresh process: modules imported earlier under ambient env keep any
    import-time constants they read then.
    """
    config = config or LabStackConfig.from_env()
    overlay = overlay or Overlay()
    settings = compose_settings(config, overlay)
    decisions = DecisionLog(run_dir / 'decisions.jsonl' if run_dir is not None else None)
    typesense_up = peer_listening(config.typesense) if install_product else True
    if not typesense_up:
        settings.update(TYPESENSE_DOWN_ENV)
    policy = network_policy or NetworkPolicy.for_stack(
        config, on_refusal=lambda row: decisions.record('network_refused', row['kind'], 'network', once=False, **row)
    )
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, settings, clear=True))
        stack.enter_context(guarded_network(policy))
        environment = LabEnvironment(
            config=config,
            overlay=overlay,
            decisions=decisions,
            network=policy,
            clock=clock,
            stack=stack,
            run_dir=run_dir,
            settings=settings,
        )
        decisions.record('overlay', overlay.digest(), 'overlay', overlay_name=overlay.name)
        if not typesense_up:
            decisions.record(
                'typesense_unavailable',
                'conversation_index_writes_off',
                'lab_peer_probe',
                port=config.typesense[1],
            )
        if install_product:
            import importlib

            import google.auth

            for module_name in preimport:
                importlib.import_module(module_name)

            stack.enter_context(patch.object(google.auth, 'default', _refuse))
            resolve_pins(overlay, decisions, environ=os.environ, uid=config.uid)
            trace_serving_for(stack, overlay, decisions)
            install_gate_pins(stack, overlay, decisions)
            environment.firestore = firestore_client if firestore_client is not None else _emulator_firestore(config)
            _install_firestore(stack, environment.firestore)
            if redis_client is None:
                import redis
                from database.redis_connection import redis_connection_kwargs

                # Same construction as database.redis_db.r, under the lab env (bytes, not str).
                redis_client = redis.Redis(**redis_connection_kwargs())
                stack.callback(redis_client.close)
            environment.redis = redis_client
            _install_redis(stack, redis_client)
            environment.storage = _install_storage(stack, config.storage_root)
        if clock is not None:
            stack.enter_context(installed_clock(clock))
        yield environment
