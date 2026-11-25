"""File-backed USD spend ledger with a hard cap (ported from owner_lab ``SpendLedger``).

Every billable attempt (an LLM call through the lab proxy, an STT vendor call)
reserves its worst case *before* anything is sent. A reservation that would push
committed spend (settled + in flight) past the cap is refused with
``SpendCapReached``, so a crash or a hung request can never overspend. ``settle``
replaces a reservation with the measured cost; ``release`` drops one whose request
was provably never sent. A request whose fate is unknown (transport error after
send) keeps its reservation: that is the owner_lab rule.

The ledger is one JSON file updated under ``flock``, safe across the proxy's
threads and stage subprocesses. Default cap: $5 per run (DESIGN L6).

Ingest/chain lanes may type against ``SpendGuard`` instead of importing this class.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from testing.pipeline_lab.contracts import utc_iso
from testing.pipeline_lab.store import atomic_write_json, locked, read_json

DEFAULT_BUDGET_USD = 5.0


class SpendCapReached(Exception):
    """Terminal for the run: the reservation would exceed the hard cap."""

    def __init__(self, detail: str = 'spend cap reached'):
        super().__init__(detail)


@dataclass(frozen=True)
class Reservation:
    id: str
    usd: float
    purpose: str


class SpendGuard(Protocol):
    def reserve(self, usd: float, *, purpose: str) -> Reservation: ...

    def settle(self, reservation: Reservation, usd: float) -> None: ...

    def release(self, reservation: Reservation) -> None: ...


@dataclass
class SpendLedger:
    path: Path
    budget_usd: float = DEFAULT_BUDGET_USD

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        if self.budget_usd < 0:
            raise ValueError('budget must be >= 0')

    @property
    def _lock(self) -> Path:
        return self.path.with_name(self.path.name + '.lock')

    def load(self) -> dict[str, Any]:
        data = read_json(self.path, None) or {}
        return {
            'budget_usd': float(data.get('budget_usd', self.budget_usd)),
            'settled_usd': float(data.get('settled_usd') or 0.0),
            'in_flight': dict(data.get('in_flight') or {}),
            'requests': int(data.get('requests') or 0),
            'refused': int(data.get('refused') or 0),
            'updated_at': data.get('updated_at'),
        }

    def _save(self, ledger: dict[str, Any]) -> None:
        ledger['budget_usd'] = self.budget_usd
        ledger['updated_at'] = utc_iso()
        atomic_write_json(self.path, ledger)

    @staticmethod
    def committed(ledger: dict[str, Any]) -> float:
        return ledger['settled_usd'] + sum(float(row['usd']) for row in ledger['in_flight'].values())

    def snapshot(self) -> dict[str, Any]:
        ledger = self.load()
        return {
            'budget_usd': self.budget_usd,
            'settled_usd': round(ledger['settled_usd'], 6),
            'in_flight_usd': round(self.committed(ledger) - ledger['settled_usd'], 6),
            'committed_usd': round(self.committed(ledger), 6),
            'requests': ledger['requests'],
            'refused': ledger['refused'],
        }

    def spent(self) -> float:
        """Settled plus in-flight: what the run must be assumed to have spent."""
        return self.committed(self.load())

    def reserve(self, usd: float, *, purpose: str = '') -> Reservation:
        if usd < 0:
            raise ValueError('reservation must be >= 0')
        with locked(self._lock):
            ledger = self.load()
            if self.committed(ledger) + usd > self.budget_usd + 1e-12:
                ledger['refused'] += 1
                self._save(ledger)
                raise SpendCapReached(
                    f'reservation of ${usd:.4f} would exceed the ${self.budget_usd:.2f} cap '
                    f'(committed ${self.committed(ledger):.4f})'
                )
            reservation = Reservation(id=secrets.token_hex(8), usd=float(usd), purpose=purpose)
            ledger['in_flight'][reservation.id] = {'usd': reservation.usd, 'purpose': purpose, 'at': utc_iso()}
            ledger['requests'] += 1
            self._save(ledger)
            return reservation

    def settle(self, reservation: Reservation, usd: float) -> None:
        """Replace the reservation with the measured cost. Never raises on the cap: the call already happened."""
        with locked(self._lock):
            ledger = self.load()
            ledger['in_flight'].pop(reservation.id, None)
            ledger['settled_usd'] += max(0.0, float(usd))
            self._save(ledger)

    def release(self, reservation: Reservation) -> None:
        """Drop a reservation whose request was never sent."""
        with locked(self._lock):
            ledger = self.load()
            ledger['in_flight'].pop(reservation.id, None)
            self._save(ledger)

    def exhausted(self) -> bool:
        return self.committed(self.load()) >= self.budget_usd - 1e-12
