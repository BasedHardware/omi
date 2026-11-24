"""Deny-by-default network for the lab process (DESIGN L9).

Allowed: loopback connections to the configured local peers (Firestore and Auth
emulators, Redis, Typesense, the lab LLM proxy) and, only when listed, approved
STT endpoints by host name. Everything else raises :class:`LabNetworkRefused`
and is appended to the refusal log so a run can report what it tried to reach.

gRPC's C core bypasses Python sockets, so channels are checked separately: only an
insecure channel to the Firestore emulator target may open.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import socket
import threading
from typing import Callable, Iterator
from unittest.mock import patch

from testing.pipeline_lab.stack.config import LOOPBACK, LabStackConfig


class LabNetworkRefused(RuntimeError):
    """The lab refused an outbound connection. The message names only host and port."""


@dataclass
class NetworkPolicy:
    loopback_ports: frozenset[int]
    named_endpoints: frozenset[tuple[str, int]] = frozenset()
    grpc_targets: frozenset[str] = frozenset()
    refusals: list[dict] = field(default_factory=list)
    on_refusal: Callable[[dict], None] | None = None
    _resolved: set[tuple[str, int]] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def for_stack(cls, config: LabStackConfig, **kwargs) -> 'NetworkPolicy':
        return cls(
            loopback_ports=config.loopback_ports(),
            named_endpoints=frozenset(config.stt_endpoints),
            grpc_targets=frozenset({config.firestore_host, f'localhost:{config.firestore[1]}'}),
            **kwargs,
        )

    def _refuse(self, kind: str, host: object, port: object) -> None:
        row = {'kind': kind, 'host': str(host), 'port': port}
        with self._lock:
            self.refusals.append(row)
        if self.on_refusal is not None:
            try:
                self.on_refusal(row)
            except Exception:
                pass
        raise LabNetworkRefused(f'pipeline lab refuses {kind} to {host}:{port}')

    def host_allowed_for_dns(self, host: object) -> bool:
        if isinstance(host, bytes):
            host = host.decode('idna', 'replace')
        if not isinstance(host, str):
            return host is None
        name = host.strip('[]').lower().rstrip('.')
        return name in LOOPBACK or name == '' or any(name == named for named, _ in self.named_endpoints)

    def address_allowed(self, host: object, port: object) -> bool:
        if isinstance(host, bytes):
            host = host.decode('idna', 'replace')
        if not isinstance(host, str) or not isinstance(port, int):
            return False
        name = host.strip('[]').lower()
        if name in LOOPBACK or name.startswith('127.'):
            return port in self.loopback_ports
        with self._lock:
            if (name, port) in self._resolved:
                return True
        return (name, port) in self.named_endpoints

    def note_resolution(self, host: str, port: object, infos: list) -> None:
        """Admit the IPs an allowlisted STT name resolved to, for that port only."""
        if not isinstance(port, int):
            try:
                port = int(port)
            except (TypeError, ValueError):
                return
        name = host.strip('[]').lower().rstrip('.')
        if (name, port) not in self.named_endpoints:
            return
        with self._lock:
            for info in infos:
                address = info[4]
                if isinstance(address, tuple) and address:
                    self._resolved.add((str(address[0]).lower(), port))

    def check_connect(self, sock: socket.socket, address: object) -> None:
        if getattr(socket, 'AF_UNIX', None) is not None and sock.family == socket.AF_UNIX:
            return
        if not isinstance(address, tuple) or len(address) < 2:
            self._refuse('connect', address, None)
        if not self.address_allowed(address[0], address[1]):
            self._refuse('connect', address[0], address[1])

    def check_grpc_target(self, target: object) -> str:
        if isinstance(target, bytes):
            target = target.decode('ascii', 'replace')
        if target not in self.grpc_targets:
            self._refuse('grpc', target, None)
        return target  # type: ignore[return-value]


@contextmanager
def guarded_network(policy: NetworkPolicy) -> Iterator[NetworkPolicy]:
    """Install the policy on sockets, DNS and gRPC for the duration of the block."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_create_connection = socket.create_connection

    def connect(sock, address):
        policy.check_connect(sock, address)
        return original_connect(sock, address)

    def connect_ex(sock, address):
        policy.check_connect(sock, address)
        return original_connect_ex(sock, address)

    def getaddrinfo(host, port, *args, **kwargs):
        if not policy.host_allowed_for_dns(host):
            policy._refuse('dns', host, port)
        infos = original_getaddrinfo(host, port, *args, **kwargs)
        if isinstance(host, str):
            policy.note_resolution(host, port, infos)
        return infos

    def create_connection(address, *args, **kwargs):
        if isinstance(address, tuple) and len(address) >= 2:
            host, port = address[0], address[1]
            if not policy.host_allowed_for_dns(host) and not policy.address_allowed(host, port):
                policy._refuse('connect', host, port)
        return original_create_connection(address, *args, **kwargs)

    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, 'connect', connect))
        stack.enter_context(patch.object(socket.socket, 'connect_ex', connect_ex))
        stack.enter_context(patch.object(socket, 'getaddrinfo', getaddrinfo))
        stack.enter_context(patch.object(socket, 'create_connection', create_connection))
        try:
            import grpc
        except ImportError:  # pragma: no cover - grpc is a product dependency
            grpc = None
        if grpc is not None:
            original_insecure = grpc.insecure_channel

            def insecure_channel(target, *args, **kwargs):
                return original_insecure(policy.check_grpc_target(target), *args, **kwargs)

            def secure_channel(target, *args, **kwargs):
                policy._refuse('grpc-secure', target, None)

            stack.enter_context(patch.object(grpc, 'insecure_channel', insecure_channel))
            stack.enter_context(patch.object(grpc, 'secure_channel', secure_channel))
        yield policy
