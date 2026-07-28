"""Default-deny egress guard with explicit loopback allow-list and logging.

Patches TCP connection-oriented entrypoints (connect, connect_ex,
create_connection), DNS resolution (getaddrinfo, gethostbyname,
gethostbyname_ex), and UDP unconnected sends (sendto, sendmsg) in the Python
SUT / runner / loopback processes.  Every attempt is logged then allowed or
denied.

FEASIBILITY-ONLY: process-level socket monkeypatch; cannot observe egress from
non-Python dependency processes (Redis server, Firestore emulator JVM).  Those
are bind-constrained to loopback by the runner and excluded from
per-connection observation.  The attestation states this scope explicitly.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- #
# Allow-list model
# --------------------------------------------------------------------------- #


def _canonical_host(host: object) -> str:
    """Normalize a connection host to its canonical string identity for exact
    host+port matching against the declared allow-list.

    Identity is preserved, NOT folded to loopback: an undeclared ``localhost`` or
    ``::1`` alias must not canonicalize to a declared ``127.0.0.1``. Only bytes
    decoding and bracket/whitespace stripping are applied so the comparison is
    against the exact declared endpoint identity.
    """
    if host is None:
        return ""
    if isinstance(host, bytes):
        host = host.decode("idna", errors="replace")
    return str(host).strip().strip("[]")


def _parse_allow_list(raw: str) -> frozenset[tuple[str, int]]:
    """Parse a JSON list of {"host": "127.0.0.1", "port": 51001} entries.

    Returns the set of allowed canonical (host, port) endpoints — host identity
    is preserved so an undeclared ``localhost``/``::1`` alias on a declared port
    is NOT accepted. The DNS guard separately enforces loopback for resolution.
    """
    if not raw:
        return frozenset()
    endpoints: set[tuple[str, int]] = set()
    for item in json.loads(raw):
        endpoints.add((_canonical_host(item["host"]), int(item["port"])))
    return frozenset(endpoints)


def _is_loopback(host: object) -> bool:
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("idna", errors="replace")
    if not isinstance(host, str):
        return False
    normalized = host.strip().strip("[]").lower()
    if normalized in {"", "localhost"}:
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address.is_loopback


def _host_from_address(address: object) -> object:
    if isinstance(address, tuple) and address:
        return address[0]
    return address


def _is_unix_socket(sock: socket.socket) -> bool:
    af_unix = getattr(socket, "AF_UNIX", None)
    return af_unix is not None and sock.family == af_unix


# --------------------------------------------------------------------------- #
# Evidence sink (interprocess-safe, sanitized)
# --------------------------------------------------------------------------- #

_FORBIDDEN_KEYS = frozenset(
    {"audio", "audio_bytes", "body", "file_path", "payload", "raw_blob_paths", "text", "transcript", "uid"}
)

_sink_lock = threading.Lock()


def _make_sink(state_dir: str, role: str) -> Callable[[dict[str, Any]], None]:
    evidence_path = Path(state_dir) / "evidence" / "egress.jsonl"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)

    def sink(record: dict[str, Any]) -> None:
        sanitized = {k: v for k, v in record.items() if k not in _FORBIDDEN_KEYS}
        sanitized["role"] = role
        sanitized.setdefault("ts", time.monotonic())
        line = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
        with _sink_lock:
            import fcntl

            with evidence_path.open("a") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                fh.write(line + "\n")
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    return sink


# --------------------------------------------------------------------------- #
# Default-deny guard installation
# --------------------------------------------------------------------------- #

_original_sendto = socket.socket.sendto
_original_sendmsg = socket.socket.sendmsg
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_create_connection = socket.create_connection
_original_getaddrinfo = socket.getaddrinfo
_original_gethostbyname = socket.gethostbyname
_original_gethostbyname_ex = socket.gethostbyname_ex


def install_default_deny_guard(
    *, role: str, allow: frozenset[tuple[str, int]], sink: Callable[[dict[str, Any]], None]
) -> None:
    """Patch socket entrypoints: default-deny, allow only declared canonical
    host+port endpoints, log every attempt. Undeclared loopback aliases
    (localhost/::1) on a declared port are denied."""

    def _check_and_log(sock: socket.socket | None, address: object) -> bool:
        host = _host_from_address(address)
        port = None
        if isinstance(address, tuple) and len(address) >= 2 and isinstance(address[1], int):
            port = address[1]
        is_unix = _is_unix_socket(sock) if sock is not None else False
        is_lb = is_unix or _is_loopback(host)
        if is_unix:
            in_allow = True
        elif port is not None:
            # Enforce canonical host+port endpoint identity, not port alone: an
            # undeclared localhost/::1 alias on a declared port is denied.
            in_allow = (_canonical_host(host), port) in allow
        else:
            in_allow = False
        sink(
            {
                "event": "egress_attempt",
                "host": str(host) if host is not None else "",
                "port": port,
                "loopback": is_lb,
                "decision": "allow" if in_allow else "deny",
            }
        )
        return in_allow

    def guarded_connect(sock: socket.socket, address: object) -> Any:
        if not _check_and_log(sock, address):
            raise OSError(f"[replay-harness] denied egress to {_host_from_address(address)!r}:{address}")
        return _original_connect(sock, address)

    def guarded_connect_ex(sock: socket.socket, address: object) -> int:
        if not _check_and_log(sock, address):
            return -1  # connect_ex returns error code, not exception
        return _original_connect_ex(sock, address)

    def guarded_create_connection(address: object, *args: Any, **kwargs: Any) -> socket.socket:
        if not _check_and_log(None, address):
            raise OSError(f"[replay-harness] denied egress to {address!r}")
        return _original_create_connection(address, *args, **kwargs)

    def guarded_sendto(sock: socket.socket, data: Any, *args: Any) -> Any:
        # sendto(data, address) or sendto(data, flags, address); address is last positional.
        if args:
            address = args[-1]
            if isinstance(address, tuple) and not _check_and_log(sock, address):
                raise OSError(f"[replay-harness] denied UDP sendto to {_host_from_address(address)!r}:{address}")
        return _original_sendto(sock, data, *args)

    def guarded_sendmsg(
        sock: socket.socket, buffers: Any, ancdata: Any = (), flags: int = 0, address: Any = None
    ) -> Any:
        if isinstance(address, tuple) and not _check_and_log(sock, address):
            raise OSError(f"[replay-harness] denied UDP sendmsg to {_host_from_address(address)!r}:{address}")
        return _original_sendmsg(sock, buffers, ancdata, flags, address)

    def guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        # DNS resolution to non-loopback is always denied; loopback is always allowed
        # (the port-level check happens at connect time).
        is_lb = _is_loopback(host)
        sink(
            {
                "event": "dns_attempt",
                "host": str(host) if host is not None else "",
                "loopback": is_lb,
                "decision": "allow" if is_lb else "deny",
            }
        )
        if not is_lb:
            raise OSError(f"[replay-harness] denied DNS for {host!r}")
        return _original_getaddrinfo(host, *args, **kwargs)

    def guarded_gethostbyname(host: object) -> Any:
        is_lb = _is_loopback(host)
        sink({"event": "dns_attempt", "host": str(host), "loopback": is_lb, "decision": "allow" if is_lb else "deny"})
        if not is_lb:
            raise OSError(f"[replay-harness] denied DNS for {host!r}")
        return _original_gethostbyname(host)

    def guarded_gethostbyname_ex(host: object) -> Any:
        is_lb = _is_loopback(host)
        sink({"event": "dns_attempt", "host": str(host), "loopback": is_lb, "decision": "allow" if is_lb else "deny"})
        if not is_lb:
            raise OSError(f"[replay-harness] denied DNS for {host!r}")
        return _original_gethostbyname_ex(host)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.create_connection = guarded_create_connection
    socket.socket.sendto = guarded_sendto
    socket.socket.sendmsg = guarded_sendmsg
    socket.getaddrinfo = guarded_getaddrinfo
    socket.gethostbyname = guarded_gethostbyname
    socket.gethostbyname_ex = guarded_gethostbyname_ex


def guard_from_env() -> Callable[[dict[str, Any]], None] | None:
    """Read role + allow-list + state-dir from env and install the guard.

    Returns the sink callable if installed, None otherwise.
    """
    role = os.getenv("OMI_REPLAY_ROLE", "").strip()
    state_dir = os.getenv("OMI_REPLAY_STATE_DIR", "").strip()
    allow_raw = os.getenv("OMI_REPLAY_EGRESS_ALLOW", "").strip()
    if not role or not state_dir:
        return None
    allow = _parse_allow_list(allow_raw)
    sink = _make_sink(state_dir, role)
    install_default_deny_guard(role=role, allow=allow, sink=sink)
    sink({"event": "guard_installed", "role": role, "allow_count": len(allow)})
    return sink
