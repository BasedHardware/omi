"""Mock utils.other.task — identical to production (this IS the leak source).

Improvement #2: Task counters — tracks created/done/cancelled/in_flight/max_in_flight
to prove leak 1 (untracked fire-and-forget tasks) accumulates in vulnerable code.
"""

import asyncio

# Global task metrics — accessible via get_task_metrics() from /debug/memory
_task_metrics = {
    'created': 0,
    'done': 0,
    'cancelled': 0,
    'in_flight': 0,
    'max_in_flight': 0,
}


def get_task_metrics():
    """Return a copy of current task metrics."""
    return dict(_task_metrics)


def safe_create_task(t):
    _task_metrics['created'] += 1
    _task_metrics['in_flight'] += 1
    if _task_metrics['in_flight'] > _task_metrics['max_in_flight']:
        _task_metrics['max_in_flight'] = _task_metrics['in_flight']

    task = asyncio.create_task(t)

    def on_done(tt):
        _task_metrics['in_flight'] -= 1
        if tt.cancelled():
            _task_metrics['cancelled'] += 1
        else:
            _task_metrics['done'] += 1
            exc = tt.exception()
            if exc:
                print("Unhandled exception in background task:", exc)

    task.add_done_callback(on_done)
    return task
