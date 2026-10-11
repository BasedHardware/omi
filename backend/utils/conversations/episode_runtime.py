"""Durable-job scope for extended note budgets; synchronous request paths stay bounded."""

from contextvars import ContextVar

_durable_job: ContextVar[bool] = ContextVar('episode_durable_job', default=False)


def process_with_episode_budget(process, *args, **kwargs):
    token = _durable_job.set(True)
    try:
        return process(*args, **kwargs)
    finally:
        _durable_job.reset(token)


def durable_episode_job():
    return _durable_job.get()
