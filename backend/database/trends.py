from datetime import datetime
from typing import Dict, List

from firebase_admin import firestore
from google.api_core.retry import Retry

from models.memory import Memory
from models.trend import Trend, valid_items
from ._client import db, document_id_from_seed


def get_trends_data() -> List[Dict]:
    trends_ref = db.collection('trends')
    trends_docs = [doc for doc in trends_ref.stream(retry=Retry())]
    trends_data = []
    for category in trends_docs:
        try:
            category_data = category.to_dict()
            if category_data['category'] not in ['ceo', 'company', 'software_product', 'hardware_product',
                                                 'ai_product']:
                continue

            category_topics_ref = trends_ref.document(category_data['id']).collection('topics')
            topics_docs = [topic.to_dict() for topic in category_topics_ref.stream(retry=Retry())]
            cleaned_topics = []
            topics = sorted(topics_docs, key=lambda e: len(e['memory_ids']), reverse=True)
            for topic in topics:
                if topic['topic'] not in valid_items:
                    continue
                topic['memories_count'] = len(topic['memory_ids'])
                del topic['memory_ids']
                cleaned_topics.append(topic)

            category_data['topics'] = cleaned_topics
            trends_data.append(category_data)
        except Exception as e:
            print(e)
            continue

    return trends_data


def save_trends(memory: Memory, trends: List[Trend]):
    trends_coll_ref = db.collection('trends')

    for trend in trends:
        category = trend.category.value
        topics = trend.topics
        trend_type = trend.type.value
        category_id = document_id_from_seed(category + trend_type)
        category_doc_ref = trends_coll_ref.document(category_id)

        category_doc_ref.set(
            {"id": category_id, "category": category, "type": trend_type, "created_at": datetime.utcnow()},
            merge=True
        )

        topics_coll_ref = category_doc_ref.collection('topics')

        for topic in topics:
            topic_id = document_id_from_seed(topic)
            topic_doc_ref = topics_coll_ref.document(topic_id)

            topic_doc_ref.set({"id": topic_id, "topic": topic}, merge=True)
            topic_doc_ref.update({'memory_ids': firestore.firestore.ArrayUnion([memory.id])})
