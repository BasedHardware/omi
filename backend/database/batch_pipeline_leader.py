"""Transactional ownership witness shared by strict maintenance callers."""

from dataclasses import dataclass
from collections.abc import Callable


class LeaseLost(RuntimeError):
    """Discovery must stop; durable group custody is unaffected."""


@dataclass(frozen=True)
class LeaseGuard:
    role: str
    holder: str
    token: str
    clock: Callable[[], float]

    def check(self, tx):
        row = tx.get('leases', self.role)
        if (
            row.get('holder') != self.holder
            or row.get('token') != self.token
            or float(row.get('expires_at') or 0) <= self.clock()
        ):
            raise LeaseLost('scan ownership lost')
