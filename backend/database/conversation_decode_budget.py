"""Optional byte allowance for expanding stored conversation payloads."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import zlib


class DecodeBudgetExceeded(RuntimeError):
    """The caller cannot safely expand another stored payload."""


@dataclass
class DecodeBudget:
    remaining: int

    @contextmanager
    def activate(self):
        token = _budget.set(self)
        try:
            yield
        finally:
            _budget.reset(token)


_budget: ContextVar[DecodeBudget | None] = ContextVar('conversation_decode_budget', default=None)


def remaining_bytes() -> int | None:
    budget = _budget.get()
    return budget.remaining if budget is not None else None


def charge_bytes(size: int) -> None:
    budget = _budget.get()
    if budget is not None:
        if size > budget.remaining:
            raise DecodeBudgetExceeded()
        budget.remaining -= size


def decompress(payload: bytes) -> bytes:
    limit = remaining_bytes()
    if limit is None:
        return zlib.decompress(payload)
    decoder = zlib.decompressobj()
    plaintext = decoder.decompress(payload, limit + 1)
    if len(plaintext) > limit or decoder.unconsumed_tail:
        raise DecodeBudgetExceeded()
    if not decoder.eof:
        raise zlib.error('Truncated compressed conversation payload')
    charge_bytes(len(plaintext))
    return plaintext
