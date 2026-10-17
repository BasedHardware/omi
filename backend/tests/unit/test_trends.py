from unittest.mock import MagicMock
from models.trend import Trend, TrendEnum, TrendType
from database.trends import get_trends_data, save_trends


def test_get_trends_data_success(monkeypatch):
    import database.trends as tr

    monkeypatch.setattr(tr, "valid_items", {"TechTopic1", "TechTopic2"})

    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_client.collection.return_value = mock_coll

    cat_doc = MagicMock()
    cat_doc.id = "cat_1"
    cat_doc.to_dict.return_value = {"id": "cat_1", "category": "software_product"}

    mock_coll.stream.return_value = [cat_doc]

    topic_doc_1 = MagicMock()
    topic_doc_1.to_dict.return_value = {
        "id": "top_1",
        "topic": "TechTopic1",
        "memory_ids": ["mem1", "mem2"],
    }

    topic_doc_2 = MagicMock()
    topic_doc_2.to_dict.return_value = {
        "id": "top_2",
        "topic": "TechTopic2",
        "memory_ids": ["mem3"],
    }

    mock_cat_doc_ref = MagicMock()
    mock_coll.document.return_value = mock_cat_doc_ref
    mock_cat_doc_ref.collection.return_value.stream.return_value = [topic_doc_2, topic_doc_1]

    trends = get_trends_data(firestore_client=mock_client)
    assert len(trends) == 1
    assert trends[0]["category"] == "software_product"
    topics = trends[0]["topics"]
    assert len(topics) == 2
    # Sorted by memories_count descending
    assert topics[0]["topic"] == "TechTopic1"
    assert topics[0]["memories_count"] == 2
    assert "memory_ids" not in topics[0]
    assert topics[1]["topic"] == "TechTopic2"
    assert topics[1]["memories_count"] == 1


def test_get_trends_data_none_client():
    assert get_trends_data(firestore_client=None) == []


def test_get_trends_data_stream_exception():
    mock_client = MagicMock()
    mock_client.collection.side_effect = RuntimeError("Stream timeout")

    assert get_trends_data(firestore_client=mock_client) == []


def test_get_trends_data_skips_invalid_categories():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_client.collection.return_value = mock_coll

    cat_doc = MagicMock()
    cat_doc.to_dict.return_value = {"id": "cat_inv", "category": "unsupported_category"}
    mock_coll.stream.return_value = [cat_doc]

    trends = get_trends_data(firestore_client=mock_client)
    assert trends == []


def test_get_trends_data_missing_id_in_payload(monkeypatch):
    import database.trends as tr

    monkeypatch.setattr(tr, "valid_items", {"TechTopic1"})

    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_client.collection.return_value = mock_coll

    cat_doc = MagicMock()
    cat_doc.id = "fallback_doc_id"
    # 'id' is missing in dictionary payload
    cat_doc.to_dict.return_value = {"category": "ai_product"}
    mock_coll.stream.return_value = [cat_doc]

    mock_cat_doc_ref = MagicMock()
    mock_coll.document.return_value = mock_cat_doc_ref
    mock_cat_doc_ref.collection.return_value.stream.return_value = []

    trends = get_trends_data(firestore_client=mock_client)
    assert len(trends) == 1
    mock_coll.document.assert_called_with("fallback_doc_id")


def test_get_trends_data_handles_malformed_topic_memory_ids(monkeypatch):
    import database.trends as tr

    monkeypatch.setattr(tr, "valid_items", {"TechTopic1"})

    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_client.collection.return_value = mock_coll

    cat_doc = MagicMock()
    cat_doc.id = "cat_1"
    cat_doc.to_dict.return_value = {"id": "cat_1", "category": "ceo"}
    mock_coll.stream.return_value = [cat_doc]

    topic_doc = MagicMock()
    topic_doc.to_dict.return_value = {
        "id": "top_1",
        "topic": "TechTopic1",
        "memory_ids": 12345,  # Malformed non-list
    }

    mock_cat_doc_ref = MagicMock()
    mock_coll.document.return_value = mock_cat_doc_ref
    mock_cat_doc_ref.collection.return_value.stream.return_value = [topic_doc]

    trends = get_trends_data(firestore_client=mock_client)
    assert len(trends) == 1
    assert trends[0]["topics"][0]["memories_count"] == 0


def test_save_trends_success():
    mock_client = MagicMock()
    mock_coll = MagicMock()
    mock_cat_doc = MagicMock()
    mock_topic_coll = MagicMock()
    mock_topic_doc = MagicMock()

    mock_client.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_cat_doc
    mock_cat_doc.collection.return_value = mock_topic_coll
    mock_topic_coll.document.return_value = mock_topic_doc

    trend = Trend(
        category=TrendEnum.software_product,
        type=TrendType.best,
        topics=["Docker", "  Kubernetes  ", ""],
    )

    save_trends("mem_999", [trend], firestore_client=mock_client)

    mock_client.collection.assert_called_with("trends")
    mock_cat_doc.set.assert_called()
    assert mock_topic_doc.set.call_count == 2
    assert mock_topic_doc.update.call_count == 2


def test_save_trends_empty_inputs():
    mock_client = MagicMock()

    # Empty memory id
    save_trends("", [MagicMock()], firestore_client=mock_client)
    save_trends("   ", [MagicMock()], firestore_client=mock_client)
    mock_client.collection.assert_not_called()

    # Empty trends list
    save_trends("mem_123", [], firestore_client=mock_client)
    mock_client.collection.assert_not_called()
