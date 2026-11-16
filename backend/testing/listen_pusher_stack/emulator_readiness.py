"""Bounded readiness probe for the gauntlet's Firestore emulator.

The Firestore emulator's port is open, and already answers plain HTTP/1.1
(``GET /`` returns ``Ok``), several seconds before it serves the Firestore gRPC
surface. A port check therefore proves nothing: a gRPC client that arrives in
that window sees an HTTP/1.1 responder and fails with
``Trying to connect an http1.x server (HTTP status 400)``, and the client's
default retry wrapper turns that into an opaque 60-second
``google.api_core.exceptions.RetryError``.

This probe issues one real Firestore RPC per attempt with backoff. It runs
inside the Firebase emulator session (``firebase emulators:exec``), before the
gauntlet's inner command, so the gauntlet only ever starts against a serving
emulator.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from google.cloud import firestore

DEFAULT_PROJECT = 'demo-omi-listen-stack'
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_RPC_TIMEOUT_SECONDS = 5.0
# Not a `__`-prefixed name: the Firestore emulator reserves those ids and
# answers InvalidArgument, which would look exactly like an unready emulator.
READINESS_COLLECTION = 'stack_readiness_probe'


class EmulatorNotReady(RuntimeError):
    """The endpoint is not serving the Firestore gRPC surface."""


def endpoint_from_env(variable: str = 'FIRESTORE_EMULATOR_HOST') -> tuple[str, int]:
    value = os.getenv(variable, '').strip()
    if not value:
        raise EmulatorNotReady(f'{variable} is not set; the probe must run inside `firebase emulators:exec`')
    host, _, port = value.rpartition(':')
    if not host or not port.isdigit():
        raise EmulatorNotReady(f'{variable} is not host:port: {value!r}')
    return host, int(port)


def _summary(error: BaseException) -> str:
    return str(error).splitlines()[0][:400] if str(error) else type(error).__name__


def probe_once(*, rpc_timeout: float = DEFAULT_RPC_TIMEOUT_SECONDS, project: str = DEFAULT_PROJECT) -> None:
    """Prove the emulator answers a real Firestore RPC exactly once.

    ``retry=None`` is load-bearing: the default gRPC retry policy spends up to
    60 seconds on transport errors, which is the ``RetryError`` this probe
    exists to replace. A document that does not exist is a successful probe:
    the call returns ``None`` once the service answered.
    """
    client = firestore.Client(project=project)
    client.collection(READINESS_COLLECTION).document('probe').get(timeout=rpc_timeout, retry=None)


def wait_until_serving(
    *,
    host: str | None = None,
    port: int | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    rpc_timeout: float = DEFAULT_RPC_TIMEOUT_SECONDS,
    project: str = DEFAULT_PROJECT,
) -> tuple[str, int]:
    """Probe with exponential backoff until the emulator serves or the budget ends."""
    if host is None or port is None:
        host, port = endpoint_from_env()
    deadline = time.monotonic() + max(timeout, 0.0)
    delay = 0.1
    attempt = 0
    last_error: BaseException | None = None
    while True:
        attempt += 1
        try:
            probe_once(rpc_timeout=rpc_timeout, project=project)
            return host, port
        except Exception as error:  # any transport/protocol error means "not ready yet"
            last_error = error
            print(
                f'[emulator] readiness probe {attempt} on {host}:{port}: {type(error).__name__}: {_summary(error)}',
                file=sys.stderr,
                flush=True,
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 2.0)
    raise EmulatorNotReady(
        f'{host}:{port} did not serve Firestore gRPC within {timeout:.0f}s; '
        f'last error: {type(last_error).__name__}: {_summary(last_error) if last_error else "no attempt ran"}'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument('--rpc-timeout', type=float, default=DEFAULT_RPC_TIMEOUT_SECONDS)
    parser.add_argument('--project', default=DEFAULT_PROJECT)
    args = parser.parse_args(argv)
    try:
        host, port = wait_until_serving(timeout=args.timeout, rpc_timeout=args.rpc_timeout, project=args.project)
    except EmulatorNotReady as error:
        print(f'[emulator] not ready: {error}', file=sys.stderr, flush=True)
        return 1
    print(f'[emulator] Firestore emulator serving gRPC on {host}:{port}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
