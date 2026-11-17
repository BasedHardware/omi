"""One bounded table/source per supervised serving tick; Firestore remains primary."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import threading
import time

from database.jobstore.copy_connections import copy_pools
from database.jobstore.dual_store import DualStore, MIRRORED_TABLES
from database.jobstore.index_store import connection_deadline
from database.jobstore.postgres_store import PostgresStore
from database.jobstore.reconcile import process_page
from database.jobstore.retirement_cursor import CursorPage, CursorScope
from database.batch_pipeline_retirement_metrics import RetirementPageReason, observe, page_error
from utils.staging_fence import (
    PROD_JOBSTORE_NAMESPACE,
    is_staging,
    jobstore_production_context_matches,
    jobstore_production_mirror_configured,
    jobstore_shadow_admits,
)

# Includes warmup, cursor lock/read, page, and advance; far below the 60s lease.
TICK_BUDGET_SECONDS = 10.0
WARMUP_SECONDS = 5.0


@dataclass(frozen=True)
class Settings:
    rows: int
    reads: int
    statements: int
    page_seconds: float
    interval_seconds: float

    @classmethod
    def from_env(cls):
        values = cls(
            int(os.getenv('JOBSTORE_RETIREMENT_MAX_ROWS', '10')),
            int(os.getenv('JOBSTORE_RETIREMENT_MAX_PRIMARY_READS', '20')),
            int(os.getenv('JOBSTORE_RETIREMENT_MAX_STATEMENTS', '500')),
            float(os.getenv('JOBSTORE_RETIREMENT_PAGE_SECONDS', '3')),
            float(os.getenv('JOBSTORE_RETIREMENT_INTERVAL_SECONDS', '20')),
        )
        if not (
            1 <= values.rows <= 1000
            and 2 <= values.reads <= 2000
            and 10 <= values.statements <= 20000
            and math.isfinite(values.page_seconds)
            and 0 < values.page_seconds <= 3
            and math.isfinite(values.interval_seconds)
            and 20 <= values.interval_seconds <= 3600
        ):
            raise ValueError('invalid retirement budgets')
        return values


def configured_target() -> tuple[str, str, str] | None:
    if os.getenv('JOBSTORE_RETIREMENT_ENABLED', 'on').strip().lower() in {'0', 'false', 'off', 'no'}:
        return None
    target = tuple(
        os.getenv(name, '').strip() for name in ('JOBSTORE_PG_HOST', 'JOBSTORE_PG_DATABASE', 'JOBSTORE_PG_USER')
    )
    if not any(target):
        return None
    if not all(target):
        raise ValueError('incomplete retirement target')
    return target[0], target[1], target[2]


class Retirement:
    def __init__(self):
        self._lock = threading.Lock()
        self._due = 0.0
        self._position = 0
        self._dual = None

    def tick(self, store) -> None:
        # The serving lease limits contention; this local lock limits overlapping
        # calls on one instance. PG row lock + version CAS is the durable fence.
        if not self._lock.acquire(blocking=False):
            return
        namespace = getattr(store, 'namespace', '')
        source, table = 'copy', 'jobs'
        if namespace not in {'batch_pipeline_prod', 'batch_pipeline_dev'}:
            self._lock.release()
            return
        try:
            if time.monotonic() < self._due:
                return
            self._due = time.monotonic() + 20
            target = configured_target()
            if target is None:
                return
            prod = namespace == PROD_JOBSTORE_NAMESPACE and not is_staging()
            if not (jobstore_production_context_matches() if prod else jobstore_shadow_admits(namespace)):
                return
            settings = Settings.from_env()
            self._due = time.monotonic() + settings.interval_seconds
            sources = ('copy', 'primary') if prod and jobstore_production_mirror_configured() else ('copy',)
            schedule = [(src, tbl) for tbl in sorted(MIRRORED_TABLES) for src in sources]
            source, table = schedule[self._position % len(schedule)]
            self._position += 1  # A failed table must not starve other tables.
            deadline = time.monotonic() + TICK_BUDGET_SECONDS
            pools = copy_pools(*target)
            if self._dual is None:
                primary = getattr(store, 'primary', store)
                self._dual = DualStore(
                    primary,
                    PostgresStore(namespace, pool=pools.normal, customer_client=None),
                    erasure_pool=pools.erasure,
                )
            # Cold IAM setup uses a bounded connector; SQL transport uses the
            # same total tick deadline. Warmup never spends the page budget.
            warm_deadline = min(deadline, time.monotonic() + WARMUP_SECONDS)
            with pools.normal.connection(timeout=max(0.001, warm_deadline - time.monotonic())) as conn:
                with connection_deadline(conn, warm_deadline):
                    with conn.transaction():
                        conn.execute("SET LOCAL statement_timeout = '1s'")
                        exists = conn.execute("SELECT to_regclass('jobstore_retirement_cursor')").fetchone()[0]
                        if exists is None:
                            page_error(namespace, source, table, RetirementPageReason.SCHEMA_MISSING)
                            return  # No schema mutation at startup or on ticks.
            remaining = min(settings.page_seconds, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError('retirement tick budget exhausted')
            checkpoint = CursorPage(CursorScope.for_target(namespace, source, table, True, target))
            result = process_page(
                self._dual,
                source=source,
                table=table,
                max_rows=settings.rows,
                max_primary_reads=settings.reads,
                max_statements=settings.statements,
                budget_s=remaining,
                apply=True,
                load_cursor=checkpoint.load,
                advance=checkpoint.advance,
            )
            if checkpoint.timestamps is not None:
                observe(namespace, source, table, result.counts.deleted, checkpoint.timestamps)
        except ValueError:
            page_error(namespace, source, table, RetirementPageReason.INVALID_CONFIG)
        except TimeoutError:
            page_error(namespace, source, table, RetirementPageReason.TIMEOUT)
        except Exception:
            # Never export provider errors: SQL exceptions can contain cursor/keys.
            page_error(namespace, source, table, RetirementPageReason.OPERATION_FAILED)
        finally:
            self._lock.release()
