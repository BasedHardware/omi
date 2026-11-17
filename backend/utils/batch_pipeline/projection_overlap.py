"""Bounded, identifier-free sketches of already-read follow-up discovery pages.

No database IO or discovery decisions. A sketch is per scrape target, not an
exact process/row census. Epochs are encoded in register values so multiprocess
max aggregation cannot mix an old parity slot into a newer window.
"""

import hashlib
import math
import threading
import time

from prometheus_client import Counter, Gauge, REGISTRY

from config.batch_pipeline import projection_overlap_diagnostics_enabled
from database.batch_pipeline_store import FirestoreStore
from database.jobstore.dual_store import DualStore

WINDOW_SECONDS = 600
REGISTERS = 64
NAMESPACES = frozenset({'batch_pipeline_dev', 'batch_pipeline_prod'})
MODES = frozenset({'legacy', 'due'})
PREFIX = 'omi_batch_pipeline_projection_overlap'


def estimate(registers) -> float:
    """HLL64 estimate (nominal relative standard error 13%, not a hard bound)."""
    if len(registers) != REGISTERS or any(not 0 <= rank <= 59 for rank in registers):
        raise ValueError('expected 64 bounded register ranks')
    raw = 0.709 * REGISTERS**2 / sum(2.0**-rank for rank in registers)
    zeros = registers.count(0)
    return REGISTERS * math.log(REGISTERS / zeros) if zeros and raw <= 2.5 * REGISTERS else raw


def decode(values, epoch: int) -> list[int]:
    """Reject partial/stale/reused-slot sketches rather than mixing epochs."""
    if len(values) != REGISTERS or any(
        type(value) not in (int, float) or not math.isfinite(value) or value != int(value) for value in values
    ):
        raise ValueError('incomplete or invalid sketch')
    ranks = [int(value) % REGISTERS for value in values]
    if any(int(value) // REGISTERS != epoch for value in values) or any(rank > 59 for rank in ranks):
        raise ValueError('sketch belongs to another epoch')
    return ranks


class OverlapObserver:
    def __init__(self, *, registry=REGISTRY, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        # Four bounded namespace/mode scopes, two parity slots each. No row IDs retained.
        self.windows: dict[tuple[str, str, int], tuple[int, list[int]]] = {}
        labels = ['data_namespace', 'mode']
        self.registers = Gauge(
            f'{PREFIX}_register',
            'HLL64 register encoded as ten-minute epoch*64+rank; decode and validate all64 before union',
            [*labels, 'slot', 'register'],
            multiprocess_mode='max',
            registry=registry,
        )
        self.visits = Counter(
            f'{PREFIX}_visits_total',
            'Rows already read by periodic follow-up discovery, repeats included',
            labels,
            registry=registry,
        )
        self.pages = Counter(
            f'{PREFIX}_pages_total',
            'Successful observed follow-up discovery pages, including empty pages',
            labels,
            registry=registry,
        )
        self.skipped = Counter(
            f'{PREFIX}_skipped_total',
            'Observation gaps, never discovery failures',
            ['reason'],
            registry=registry,
        )

    def observe(self, namespace: str, rows: list[str], mode: str) -> None:
        if namespace not in NAMESPACES or mode not in MODES:
            return  # No unbounded namespace/task labels or non-Firestore simulation data.
        now = self.clock()
        if not math.isfinite(now) or not 0 <= now < 2**47 * WINDOW_SECONDS:
            self.skipped.labels('invalid_clock').inc()
            return
        epoch = int(now // WINDOW_SECONDS)
        slot = epoch % 2
        key = namespace, mode, slot
        with self.lock:
            previous = self.windows.get(key)
            # Wall-clock regression must not publish newer rows under an old epoch.
            newest = max((value[0] for k, value in self.windows.items() if k[:2] == key[:2]), default=-1)
            if epoch < newest:
                self.skipped.labels('clock_regressed').inc()
                return
            ranks = previous[1] if previous is not None and previous[0] == epoch else [0] * REGISTERS
            changed = set()
            if previous is None or previous[0] != epoch:
                self.windows[key] = epoch, ranks
                changed.update(range(REGISTERS))
            for row in rows:
                # Only ranks leave this function. Neither row identifiers nor hash values are retained/exported.
                digest = int.from_bytes(hashlib.sha256(f'{namespace}\0{row}'.encode()).digest()[:8], 'big')
                register, remainder = digest >> 58, digest & ((1 << 58) - 1)
                rank = 59 - remainder.bit_length()
                if rank > ranks[register]:
                    ranks[register] = rank
                    changed.add(register)
            for register in changed:
                self.registers.labels(namespace, mode, str(slot), str(register)).set(
                    epoch * REGISTERS + ranks[register]
                )
            self.visits.labels(namespace, mode).inc(len(rows))
            self.pages.labels(namespace, mode).inc()


_default_observer = None
_default_lock = threading.Lock()


def observe_page(namespace: str, rows: list[str], mode: str) -> None:
    """Telemetry failure cannot change discovery results/cursors or raise into the drain."""
    global _default_observer
    try:
        if _default_observer is None:
            with _default_lock:
                if _default_observer is None:
                    _default_observer = OverlapObserver()
        _default_observer.observe(namespace, rows, mode)
    except Exception:
        # Do not log row values or an exception payload. Export a bounded gap if possible.
        if _default_observer is not None:
            try:
                _default_observer.skipped.labels('observer_error').inc()
            except Exception:
                pass


def observer_for_store(store):
    """Observe direct Firestore or its known mirror-only wrapper; exclude index/PG discovery."""
    if not projection_overlap_diagnostics_enabled():
        return None
    if isinstance(store, FirestoreStore):
        return lambda rows, mode: observe_page(store.namespace, rows, mode)
    # DualStore delegates all serving reads to its primary. IndexStore does not
    # subclass it and is deliberately excluded: its discovery may come from PG.
    if type(store) is DualStore and isinstance(store.primary, FirestoreStore):
        return lambda rows, mode: observe_page(store.primary.namespace, rows, mode)
    return None
