"""Regression test: Task.executed_at must default to None, not an evaluated-once timestamp.

models.task.Task declared `executed_at: Optional[datetime] = datetime.now()`. A bare
datetime.now() default is evaluated once, when the class is defined, so every Task built
without an explicit executed_at shared the same process-start timestamp and looked
already-executed at a stale time (silent wrong persisted data). It now defaults to None, like
the sibling updated_at field.
"""

from datetime import datetime, timezone

from models.task import Task, TaskAction, TaskStatus


def _make(**overrides):
    data = dict(
        id='t1',
        action=TaskAction.HUME_MERSURE_USER_EXPRESSION,
        status=TaskStatus.PROCESSING,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return Task(**data)


def test_executed_at_defaults_to_none():
    assert _make().executed_at is None


def test_explicit_executed_at_is_preserved():
    dt = datetime(2024, 5, 6, 7, 8, 9, tzinfo=timezone.utc)
    assert _make(executed_at=dt).executed_at == dt
