"""Shared retained-tail proof for record admission and exact-scope repair."""

import math


def validate_record_tail(units, finished_at, *, require_finish=False):
    if not 1 <= len(units) <= 128:
        raise ValueError('retained capture unit budget exceeded')
    if finished_at is None:
        if require_finish:
            raise ValueError('retained capture finish missing')
        return
    finish = finished_at.timestamp()
    end = units[-1][0] + units[-1][1]
    if not math.isfinite(finish) or not math.isfinite(end) or end + 0.1 < finish:
        raise ValueError('retained capture tail not durable yet')
