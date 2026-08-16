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

            category_topics_ref = trends_ref.document(category_data['id']).collection('topics')
            topics_docs: List[Dict[str, Any]] = []
            for topic in category_topics_ref.stream(retry=Retry()):
                raw_topic: object = topic.to_dict()
                if isinstance(raw_topic, dict):
                    topics_docs.append(cast(Dict[str, Any], raw_topic))
            cleaned_topics: List[Dict[str, Any]] = []
            # A topic doc can be missing 'memory_ids'. save_trends writes the doc and its
            # memory_ids in two separate Firestore calls (set, then update with ArrayUnion),
            # so an interrupted or failed second write leaves a topic with no memory_ids field.
            # Treat a missing/empty value as a count of 0 so one such topic cannot raise
            # KeyError and drop the entire category from the public /v1/trends response.
            topics = sorted(topics_docs, key=lambda e: len(e.get('memory_ids') or []), reverse=True)
            for topic in topics:
                # A topic doc can be missing 'topic' the same way it can be missing 'memory_ids'
                # (guarded above); use .get so one such topic is skipped rather than raising KeyError
                # and dropping the entire category from the public /v1/trends response.
                if topic.get('topic') not in valid_items:
                    continue
                topic['memories_count'] = len(topic.get('memory_ids') or [])
                topic.pop('memory_ids', None)
                cleaned_topics.append(topic)

            category_data['topics'] = cleaned_topics
            trends_data.append(category_data)
        except Exception as e:
            logger.error(e)
            continue

    return trends_data


def save_trends(memory_id: str, trends: List[Trend]) -> None:
    trends_coll_ref = db.collection('trends')

    for trend in trends:
        category = trend.category.value
        topics = trend.topics
        trend_type = trend.type.value
        category_id = document_id_from_seed(category + trend_type)
        category_doc_ref = trends_coll_ref.document(category_id)

        category_doc_ref.set(
            {"id": category_id, "category": category, "type": trend_type, "created_at": datetime.now(timezone.utc)},
            merge=True,
        )

        topics_coll_ref = category_doc_ref.collection('topics')

        for topic in topics:
            topic_id = document_id_from_seed(topic)
            topic_doc_ref = topics_coll_ref.document(topic_id)

            topic_doc_ref.set({"id": topic_id, "topic": topic}, merge=True)
            topic_doc_ref.update({'memory_ids': firestore.firestore.ArrayUnion([memory_id])})
