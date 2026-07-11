"""Unit test for GET /v1/users/people/count.

The count uses a Firestore count() aggregation over the user's people subcollection
so a client can render a contacts badge without streaming every person (the list path
also resolves signed speech-sample URLs, which the count avoids). The endpoint itself
is a passthrough covered by the Public Developer API contract check.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.users as users_db  # noqa: E402


def test_get_people_count():
    fake_db = MagicMock()
    people_ref = fake_db.collection.return_value.document.return_value.collection.return_value
    # Firestore aggregation returns [[AggregationResult(value=...)]].
    people_ref.count.return_value.get.return_value = [[SimpleNamespace(value=4)]]

    with patch.object(users_db, "db", fake_db):
        result = users_db.get_people_count("u1")

    assert result == 4
    # Counted on the people subcollection, no streaming/build of records.
    fake_db.collection.return_value.document.return_value.collection.assert_called_with("people")
    people_ref.stream.assert_not_called()
