"""Hermetic unit tests for trends database client injection, topic update, and resilience."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
sys.path.insert(0, str(BACKEND_DIR))
from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

from models.trend import Trend, TrendEnum, TrendType, valid_items
import database.trends as trends_db


def test_get_trends_data_with_injected_client():
    names = sorted(valid_items)
    t1, t2 = names[0], names[1]

    mock_cat = MagicMock()
    mock_cat.to_dict.return_value = {"id": "cat-ai", "category": "ai_product"}

    mock_t1 = MagicMock()
    mock_t1.to_dict.return_value = {
        "id": "top-1",
        "topic": t1,
        "memory_ids": ["m1", "m2"],
    }

    mock_t2 = MagicMock()
    mock_t2.to_dict.return_value = {"id": "top-2", "topic": t2}

    mock_topics_coll = MagicMock()
    mock_topics_coll.stream.return_value = [mock_t1, mock_t2]

    mock_cat_doc = MagicMock()
    mock_cat_doc.collection.return_value = mock_topics_coll

    mock_trends_coll = MagicMock()
    mock_trends_coll.stream.return_value = [mock_cat]
    mock_trends_coll.document.return_value = mock_cat_doc

    mock_client = MagicMock()
    mock_client.collection.return_value = mock_trends_coll

    res = trends_db.get_trends_data(firestore_client=mock_client)
    assert len(res) == 1
    assert res[0]["category"] == "ai_product"
    topics = {t["topic"]: t for t in res[0]["topics"]}
    assert topics[t1]["memories_count"] == 2
    assert topics[t2]["memories_count"] == 0
    assert "memory_ids" not in topics[t1]
    assert "memory_ids" not in topics[t2]


def test_save_trends_set_and_update_with_injected_client():
    mock_cat_doc = MagicMock()
    mock_topic_doc = MagicMock()

    mock_topics_coll = MagicMock()
    mock_topics_coll.document.return_value = mock_topic_doc

    mock_cat_doc.collection.return_value = mock_topics_coll

    mock_trends_coll = MagicMock()
    mock_trends_coll.document.return_value = mock_cat_doc

    mock_client = MagicMock()
    mock_client.collection.return_value = mock_trends_coll

    names = sorted(valid_items)
    trend = Trend(
        category=TrendEnum.ai_product,
        topics=[names[0]],
        type=TrendType.best,
    )

    trends_db.save_trends("mem-123", [trend], firestore_client=mock_client)

    # Category doc set called with merge=True
    mock_cat_doc.set.assert_called_once()
    cat_payload = mock_cat_doc.set.call_args[0][0]
    assert cat_payload["category"] == "ai_product"
    assert cat_payload["type"] == "best"
    assert mock_cat_doc.set.call_args[1]["merge"] is True

    # Topic doc set called with merge=True
    mock_topic_doc.set.assert_called_once()
    topic_payload = mock_topic_doc.set.call_args[0][0]
    assert topic_payload["topic"] == names[0]
    assert mock_topic_doc.set.call_args[1]["merge"] is True

    # Topic doc update called with memory_ids ArrayUnion
    mock_topic_doc.update.assert_called_once()
    update_payload = mock_topic_doc.update.call_args[0][0]
    assert "memory_ids" in update_payload
