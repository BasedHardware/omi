from datetime import datetime, timezone
from typing import Any, Dict, List, cast

from firebase_admin import firestore
from google.api_core.retry import Retry

from models.trend import Trend, valid_items
from ._client import db, document_id_from_seed
import logging

logger = logging.getLogger(__name__)


def get_trends_data() -> List[Dict[str, Any]]:
    trends_ref = db.collection('trends')
    trends_docs = [doc for doc in trends_ref.stream(retry=Retry())]
    trends_data: List[Dict[str, Any]] = []
    for category in trends_docs:
        try:
            raw_category: object = category.to_dict()
            category_data: Dict[str, Any] = cast(Dict[str, Any], raw_category) if isinstance(raw_category, dict) else {}
            if category_data.get('category') not in [
                'ceo',
                'company',
                'software_product',
                'hardware_product',
                'ai_product',
            ]:
                continue

            category_id = category_data.get('id') or getattr(category, 'id', None)
            if not category_id:
                continue

            category_topics_ref = trends_ref.document(category_id).collection('topics')
            topics_docs: List[Dict[str, Any]] = []
            for topic in category_topics_ref.stream(retry=Retry()):
                raw_topic: object = topic.to_dict()
                if isinstance(raw_topic, dict):
                    topics_docs.append(cast(Dict[str, Any], raw_topic))
            cleaned_topics: List[Dict[str, Any]] = []

            # A topic doc can be missing 'memory_ids' if written prior to the atomic merge fix.
            # Treat a missing/empty/non-list value as a count of 0 so one such topic cannot raise
            # TypeError/KeyError and drop the entire category from the public /v1/trends response.
            def _memory_count(topic_dict: Dict[str, Any]) -> int:
                mids = topic_dict.get('memory_ids')
                return len(mids) if isinstance(mids, (list, tuple, set)) else 0

            topics = sorted(topics_docs, key=_memory_count, reverse=True)
            for topic in topics:
                # A topic doc can be missing 'topic'; use .get so one such topic is skipped
                # rather than raising KeyError and dropping the entire category from the public response.
                if topic.get('topic') not in valid_items:
                    continue
                topic['memories_count'] = _memory_count(topic)
                topic.pop('memory_ids', None)
                cleaned_topics.append(topic)

            category_data['topics'] = cleaned_topics
            trends_data.append(category_data)
        except Exception as e:
            logger.error(e)
            continue

    return trends_data


def _array_union(values: List[Any]) -> Any:
    try:
        from google.cloud.firestore_v1.transforms import ArrayUnion  # type: ignore

        return ArrayUnion(values)
    except Exception:
        pass
    fs_any: Any = firestore
    union_fn = getattr(fs_any, 'ArrayUnion', None)
    if callable(union_fn):
        return union_fn(values)
    inner_fs = getattr(fs_any, 'firestore', None)
    if inner_fs is not None:
        inner_union_fn = getattr(inner_fs, 'ArrayUnion', None)
        if callable(inner_union_fn):
            return inner_union_fn(values)
    return values


def save_trends(memory_id: str, trends: List[Trend]) -> None:
    raw_memory_id: Any = memory_id
    if not raw_memory_id or not isinstance(raw_memory_id, str) or not raw_memory_id.strip():
        return
    raw_trends: Any = trends
    if not raw_trends or not isinstance(raw_trends, list):
        return

    clean_memory_id = raw_memory_id.strip()
    trends_coll_ref = db.collection('trends')

    for trend in trends:
        if not trend:
            continue
        try:
            category = trend.category.value if hasattr(trend.category, 'value') else str(trend.category)
            topics = getattr(trend, 'topics', None) or []
            trend_type = trend.type.value if hasattr(trend.type, 'value') else str(trend.type)
        except Exception as e:
            logger.error(f"Failed to parse trend fields: {e}")
            continue

        if not category or not trend_type:
            continue

        category_id = document_id_from_seed(category + trend_type)
        category_doc_ref = trends_coll_ref.document(category_id)

        category_doc_ref.set(
            {"id": category_id, "category": category, "type": trend_type, "created_at": datetime.now(timezone.utc)},
            merge=True,
        )

        topics_coll_ref = category_doc_ref.collection('topics')

        for topic in topics:
            if not topic or not isinstance(topic, str) or not topic.strip():
                continue
            topic = topic.strip()
            topic_id = document_id_from_seed(topic)
            topic_doc_ref = topics_coll_ref.document(topic_id)

            # Atomic single-write merge replaces the former non-atomic set + update pattern,
            # cutting Firestore RPCs in half and eliminating partial topic records missing memory_ids.
            topic_doc_ref.set(
                {
                    "id": topic_id,
                    "topic": topic,
                    "memory_ids": _array_union([clean_memory_id]),
                },
                merge=True,
            )
