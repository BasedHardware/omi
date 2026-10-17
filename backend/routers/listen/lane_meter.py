"""Wall time belongs to the adopted serving lane, including flag-off controls."""

import time
from typing import Callable

from utils.observability.demand_cohort import record_metric
from utils.stt.live_metrics import DEMAND_LANE_SECONDS, DEMAND_SWITCHES


class LiveLaneMeter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.since: float | None = None
        self.lane = 'vendor'
        self.reason = 'baseline'
        self.demand_cohort = 'ineligible'

    def flush(self, *, reason: str | None = None) -> None:
        now = self.clock()
        if self.since is not None:
            record_metric(
                DEMAND_LANE_SECONDS,
                {
                    'lane': self.lane,
                    'reason': self.reason,
                    'demand_cohort': getattr(self, 'demand_cohort', 'ineligible'),
                },
                max(0, now - self.since),
            )
            self.since = now
        if reason is not None:
            self.reason = reason

    def transition(self, provider: str, *, reason: str = 'baseline') -> None:
        lane = 'parakeet' if provider == 'parakeet' else 'vendor'
        if self.since is not None and self.lane != lane:
            record_metric(DEMAND_SWITCHES, {'from_lane': self.lane, 'to_lane': lane, 'reason': reason}, 1)
        self.flush(reason=reason)
        self.since = self.clock()
        self.lane = lane

    def close(self) -> None:
        self.flush()
        self.since = None
