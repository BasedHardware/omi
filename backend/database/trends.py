from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, cast

from firebase_admin import firestore
from google.api_core.retry import Retry

from models.trend import Trend, valid_items
from ._client import db, document_id_from_seed

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = {
    'ceo',
    'company',
    'software_product',
    'hardware_product',
    'ai_product',
}


def get_trends_data(firestore_client: Optional[Any] = None) -> List[Dict[str, Any]]:
    client = firestore_client if firestore_client is not None else db
    if client is None:
        return []
    try:
        trends_ref = client.collection('trends')
        trends_docs = list(trends_ref.stream(retry=Retry()))
    except Exception as e:
        logger.exception('Failed to stream trends: %s', e)
        return []

    trends_data: List[Dict[str, Any]] = []
    for category in trends_docs:
        try:
            raw_category: object = category.to_dict()
            category_data: Dict[str, Any] = cast(Dict[str, Any], raw_category) if isinstance(raw_category, dict) else {}
            if category_data.get('category') not in _VALID_CATEGORIES:
                continue

            category_id = category_data.get('id') or getattr(category, 'id', None)
            if not category_id:
                continue

            category_topics_ref = trends_ref.document(str(category_id)).collection('topics')
            topics_docs: List[Dict[str, Any]] = []
            for topic in category_topics_ref.stream(retry=Retry()):
                raw_topic: object = topic.to_dict()
                if isinstance(raw_topic, dict):
                    topics_docs.append(cast(Dict[str, Any], raw_topic))

            cleaned_topics: List[Dict[str, Any]] = []

            def _topic_memories_len(e: Dict[str, Any]) -> int:
                m = e.get('memory_ids')
                return len(m) if isinstance(m, list) else 0

            topics = sorted(topics_docs, key=_topic_memories_len, reverse=True)
            for topic in topics:
                topic_name = topic.get('topic')
                if not isinstance(topic_name, str) or topic_name not in valid_items:
                    continue
                m = topic.get('memory_ids')
                topic['memories_count'] = len(m) if isinstance(m, list) else 0
                topic.pop('memory_ids', None)
                cleaned_topics.append(topic)

            category_data['topics'] = cleaned_topics
            trends_data.append(category_data)
        except Exception as e:
            logger.error(e)
            continue

    return trends_data


def save_trends(memory_id: str, trends: List[Trend], firestore_client: Optional[Any] = None) -> None:
    cleaned_memory_id = memory_id.strip() if memory_id else ''
    if not cleaned_memory_id or not trends:
        return

    client = firestore_client if firestore_client is not None else db
    if client is None:
        return

    trends_coll_ref = client.collection('trends')

    for trend in trends:
        try:
            category = trend.category.value
            topics = trend.topics
            trend_type = trend.type.value
            category_id = document_id_from_seed(category + trend_type)
            category_doc_ref = trends_coll_ref.document(category_id)

            category_doc_ref.set(
                {'id': category_id, 'category': category, 'type': trend_type, 'created_at': datetime.now(timezone.utc)},
                merge=True,
            )

            topics_coll_ref = category_doc_ref.collection('topics')

            for topic in topics:
                topic_clean = topic.strip()
                if not topic_clean:
                    continue
                topic_id = document_id_from_seed(topic_clean)
                topic_doc_ref = topics_coll_ref.document(topic_id)

                topic_doc_ref.set({'id': topic_id, 'topic': topic_clean}, merge=True)
                topic_doc_ref.update({'memory_ids': firestore.firestore.ArrayUnion([cleaned_memory_id])})
        except Exception as e:
            logger.error('Failed to save trend %s: %s', trend, e)
