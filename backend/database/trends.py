from datetime import datetime
from typing import Dict, List

from google.api_core.retry import Retry
from google.cloud.firestore_v1 import FieldFilter
from models.memory import Memory
from models.trend import Trend

from ._client import db, document_id_from_seed


def get_trends_data() -> Dict[str, List[Dict]]:
    trends_ref = db.collection('trends')
    trends_docs = [doc for doc in trends_ref.stream(retry=Retry())]
    trends_data = {}
    for category in trends_docs:
        cd = category.to_dict()
        trends_data[cd['category']] = []
        topic_ref = trends_ref.document(cd['id']).collection('topics')
        topics_docs = [topic for topic in topic_ref.stream(retry=Retry())]
        for topic in topics_docs:
            td = topic.to_dict()
            count = topic.reference.collection('data').count().get()[0][0].value
            trends_data[cd['category']].append({
                "topic": td['topic'],
                "count": count,
            })
    for k in trends_data.keys():
        trends_data[k] = sorted(trends_data[k], key=lambda e: e['count'], reverse=True)
    return trends_data


def save_trends(memory: Memory, trends: List[Trend]):
    mapped_trends = {trend.category.value: trend.topics for trend in trends}
    topic_data = {
        'date': memory.created_at,
        'memory_id': memory.id
    }
    print(f"topic_data: {topic_data}")
    trends_coll_ref = db.collection('trends')
    for category, topics in mapped_trends.items():
        print(f"trends.py -- category: {category}")
        category_ref = trends_coll_ref.where(
            filter=FieldFilter('category', '>=', category)).where(
            filter=FieldFilter('category', '<=', str(category + '\uf8ff'))).get()
        if len(category_ref) == 0:
            category_id = document_id_from_seed(category)
            trends_coll_ref.document(category_id).set({
                "id": category_id,
                "category": category,
                "created_at": datetime.now(),
            })
            category_ref = trends_coll_ref.where(
                filter=FieldFilter('category', '==', category)).get()
        for topic in topics:
            print(f"trends.py -- topic: {topic}")
            topic_ref = category_ref[0].reference.collection(
                'topics').where(
                filter=FieldFilter('topic', '>=', topic)).where(
                filter=FieldFilter('topic', '<=', str(topic + '\uf8ff'))).get()
            if len(topic_ref) == 0:
                topic_id = document_id_from_seed(topic)
                category_ref[0].reference.collection('topics').document(document_id_from_seed(topic)).set({
                    "id": topic_id,
                    "topic": topic
                })
                topic_ref = category_ref[0].reference.collection(
                    'topics').where(
                    filter=FieldFilter('id', '==', topic_id)).get()
            topic_ref[0].reference.collection('data').document(
                document_id_from_seed(memory.id)).set(topic_data)
