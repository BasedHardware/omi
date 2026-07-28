"""Small hermetic runner primitives for parity-pack replay tests."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Callable, Iterator

from testing.hermetic_network import BlockedNetworkError, block_outbound_network


class UnexpectedEgress(AssertionError):
    pass


class FakeHitRegistry:
    def __init__(self) -> None:
        self._hits: dict[str, int] = {}

    def hit(self, fake_name: str) -> None:
        self._hits[fake_name] = self._hits.get(fake_name, 0) + 1

    def require(self, **expected: int) -> None:
        actual = {key: self._hits.get(key, 0) for key in expected}
        if actual != expected:
            raise AssertionError(f"fake hits mismatch: expected={expected}, actual={actual}")

    @property
    def hits(self) -> dict[str, int]:
        return dict(self._hits)


@contextmanager
def deny_network() -> Iterator[None]:
    """Deny outbound network during a unit replay; always restore on cleanup.

    Delegates to the repository's validated :func:`block_outbound_network`
    guard so that low-level ``socket.connect``, ``connect_ex``, and DNS
    resolution are also blocked — not just ``socket.create_connection``.
    """
    try:
        with block_outbound_network():
            yield
    except BlockedNetworkError as exc:
        raise UnexpectedEgress(str(exc)) from exc


@contextmanager
def hermetic_run(*, cleanup: tuple[Callable[[], None], ...] = ()) -> Iterator[FakeHitRegistry]:
    """Run with egress denied and deterministic reverse-order cleanup hooks."""
    registry = FakeHitRegistry()
    try:
        with deny_network():
            yield registry
    finally:
        for hook in reversed(cleanup):
            hook()
