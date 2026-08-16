"""The lazy Typesense shim must expose the real client's surface, not just subscripts.

The shim defers client construction (offline tests import these modules with
Typesense unconfigured). A shim that only implements ``__getitem__`` silently
narrows the API: ``client.collections.create(...)`` — the only non-subscript
production caller (``utils.memory.atom_keyword_index.ensure_memories_collection``)
— then raises AttributeError, which its caller swallows, so the collection is
never auto-created and every atom upsert no-ops forever.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.conversations import search
from utils.memory import atom_keyword_index


@pytest.fixture
def fake_typesense(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace the constructed client, keeping the real shim under test."""
    fake = MagicMock()
    monkeypatch.setattr(search, "_typesense_client", None)
    monkeypatch.setattr(search, "_get_typesense_client", lambda: fake)
    return fake


def test_collections_attribute_calls_reach_the_real_client(fake_typesense: MagicMock) -> None:
    schema = {"name": "canonical_memory_atoms", "fields": []}

    search.client.collections.create(schema)

    fake_typesense.collections.create.assert_called_once_with(schema)


def test_collections_subscript_still_reaches_the_real_client(fake_typesense: MagicMock) -> None:
    search.client.collections["conversations"].documents.search({"q": "*"})

    fake_typesense.collections.__getitem__.assert_called_once_with("conversations")


def test_client_attribute_calls_reach_the_real_client(fake_typesense: MagicMock) -> None:
    search.client.multi_search.perform({}, {})

    fake_typesense.multi_search.perform.assert_called_once_with({}, {})


def test_dunder_lookups_do_not_construct_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> object:
        raise AssertionError("shim constructed a Typesense client during introspection")

    monkeypatch.setattr(search, "_get_typesense_client", explode)

    with pytest.raises(AttributeError):
        search.client.__deepcopy__
    with pytest.raises(AttributeError):
        search.client.collections.__deepcopy__


def test_ensure_memories_collection_creates_through_the_shim(
    fake_typesense: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: the real production caller creates a missing collection."""
    monkeypatch.setenv(atom_keyword_index.ATOM_KEYWORD_COLLECTION_ENV, "canonical_memory_atoms")
    fake_typesense.collections.__getitem__.return_value.retrieve.side_effect = Exception("collection missing")

    atom_keyword_index.ensure_memories_collection()

    fake_typesense.collections.create.assert_called_once()
    created_schema = fake_typesense.collections.create.call_args.args[0]
    assert created_schema["name"] == "canonical_memory_atoms"
    assert atom_keyword_index._REQUIRED_SCHEMA_FIELDS <= {field["name"] for field in created_schema["fields"]}
