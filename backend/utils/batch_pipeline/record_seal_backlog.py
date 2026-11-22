"""Refillable newest-first stock repair; canonical proofs are unchanged."""

from typing import Any

from utils.batch_pipeline import record_seal_cluster_repair as cluster
from utils.batch_pipeline.record_seal_budget import SweepBudget


class BacklogLane:
    """Checkpoint only after the previous page has been handed to row workers.

    The coordinator refills only when its pending queue is empty. A crash can
    repeat the last <=128 candidates, but cannot checkpoint past deferred work.
    Frozen horizons make each finite pass finish despite continuous arrivals.
    No account fields or seal-authority decisions are added.
    """

    def __init__(self, client, frontier, *, mode, shard=0, shards=1, progress=lambda _: None):
        self.progress = progress
        self.client, self.mode = client, mode
        self.frontier: Any = frontier  # Encrypted cursor or its lazy factory.
        self.shard, self.shards = shard, shards
        self.initialized, self.after, self.exhausted = False, None, False
        self.checkpoint_pending = False
        self.oldest_seen = 0

    def __call__(self, exclude):
        budget = SweepBudget(10)
        with cluster.silent_dependencies(), budget.interrupt_io():
            if not self.initialized:
                if callable(self.frontier):
                    self.frontier = self.frontier()
                self.after = self.frontier.read(budget)
                self.initialized = True
            elif self.mode == 'apply' and self.checkpoint_pending:
                # Includes an explicit end-of-pass reset. Never persist the
                # current page until every selected row was actually attempted.
                self.frontier.write(self.after, budget)
                self.checkpoint_pending = False
            if self.exhausted:
                return []  # One pass/run; no hot rereads of chronic refusals.
            for _ in range(8):  # <=1024 metadata reads/refill, including malformed pages.
                ages = []
                rows, saturated, cursor = cluster.discover_jobs(
                    self.client,
                    budget=budget,
                    after=self.after,
                    max_rows=128,
                    newest=True,
                    shard=self.shard,
                    shards=self.shards,
                    exclude=exclude,
                    metric_ages=ages,
                    progress=self.progress,
                )
                self.oldest_seen = max(self.oldest_seen, max(ages, default=0))
                cluster.REPAIR_OLDEST.set(self.oldest_seen)
                self.after = cursor
                self.checkpoint_pending = True
                self.exhausted = not saturated
                if rows or self.exhausted:
                    return rows
        return []
