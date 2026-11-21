"""Keep raw-row and Conversation ownership validation in agreement."""

from datetime import datetime, timezone

import pytest

from models.conversation import Conversation
from models.finalization_owner import ENGINE_FIELD, EPOCH_FIELD, python_owns_finalization
from models.structured import Structured


@pytest.mark.parametrize(
    ('markers', 'owned'),
    [
        ({}, True),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: 1}, True),
        ({ENGINE_FIELD: 'python'}, False),
        ({EPOCH_FIELD: 3}, False),
        ({ENGINE_FIELD: None, EPOCH_FIELD: 1}, False),
        ({ENGINE_FIELD: 'unknown', EPOCH_FIELD: 1}, False),
        ({ENGINE_FIELD: 'pending', EPOCH_FIELD: 1}, False),
        ({ENGINE_FIELD: 'go', EPOCH_FIELD: 1}, False),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: None}, False),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: 0}, False),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: -1}, False),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: True}, False),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: 1.0}, False),
        ({ENGINE_FIELD: 'python', EPOCH_FIELD: '1'}, False),
    ],
)
def test_python_ownership_is_strict_in_raw_rows_and_models(markers, owned):
    assert python_owns_finalization(markers) is owned
    now = datetime(2026, 11, 21, tzinfo=timezone.utc)
    row = {
        'id': 'synthetic',
        'created_at': now,
        'started_at': now,
        'finished_at': now,
        'structured': Structured(),
        **markers,
    }
    for construct in (
        lambda data: Conversation(**data),
        Conversation.model_validate,
        lambda data: Conversation.model_construct(**data),
    ):
        conversation = construct(row)
        assert conversation.python_finalization_owned is owned
        assert {ENGINE_FIELD, EPOCH_FIELD}.isdisjoint(conversation.model_dump())


def test_ownership_markers_stay_out_of_the_wire_schema():
    for mode in ('validation', 'serialization'):
        fields = Conversation.model_json_schema(mode=mode)['properties']
        assert {ENGINE_FIELD, EPOCH_FIELD}.isdisjoint(fields)
