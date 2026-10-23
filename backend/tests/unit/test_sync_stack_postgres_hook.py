"""The hermetic sync stack starts Postgres only when OMI_STACK_POSTGRES asks for it."""

import pytest

from testing.sync_cloud_tasks_stack import run


@pytest.mark.parametrize(
    'value,expected',
    [(None, False), ('', False), ('0', False), ('no', False), ('1', True), ('TRUE', True), (' on ', True)],
)
def test_postgres_is_opt_in(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv('OMI_STACK_POSTGRES', raising=False)
    else:
        monkeypatch.setenv('OMI_STACK_POSTGRES', value)
    assert run.postgres_requested() is expected
