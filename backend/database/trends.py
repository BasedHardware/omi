from datetime import datetime
from typing import Dict, List

from google.api_core.retry import Retry
from google.cloud.firestore_v1 import FieldFilter
from models.memory import Memory

from ._client import db, document_id_from_seed


def get_trends_data() -> Dict[str, List[Dict]]:
    trends_ref = db.collection('trends') # db ref
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
    print(f"trends_data pre: {trends_data}")
    for k in trends_data.keys():
        trends_data[k] = sorted(trends_data[k], key=lambda e: e['count'], reverse=True)
    print(f"trends_data post: {trends_data}")
    return trends_data


def save_trends(memory: Memory, trends: List[str]):
    mapped_trends = {trend[1]: {t[0]
                                for t in trends if t[1] == trend[1]} for trend in trends}
    print(f"trends.py -- mapped_trends: {mapped_trends}")
    topic_data = {
        'date': memory.created_at,
        'memory_id': memory.id
    }
    print(f"trend_data: {topic_data}")
    trends_coll_ref = db.collection('trends')
    for trend in trends:
        topic, category = tuple(trend)
        print(f"trends.py -- topic: {topic}, category: {category}")
        category_ref = trends_coll_ref.where(
            filter=FieldFilter('category', '>=', category)).where(
            filter=FieldFilter('category', '<=', str(category + '\uf8ff'))).get()
        if len(category_ref) == 0:
            category_id = document_id_from_seed(category)
            print(f"trends.py -- category_id: {category_id}")
            trends_coll_ref.document(category_id).set({
                "id": category_id,
                "category": category,
                "created_at": datetime.now(),
            })
            category_ref = trends_coll_ref.where(
                filter=FieldFilter('category', '==', category)).get()
        topic_id = document_id_from_seed(topic)
        print(f"trends.py -- topic_id: {topic_id}")
        print(f"trends.py -- category_ref: {category_ref}")
        if len(category_ref) > 0:
            topic_ref = category_ref[0].reference.collection(
                'topics').document(topic_id)
            topic_ref.set({
                "id": topic_id,
                "topic": topic
            })
            topic_ref.collection('data').document(
                document_id_from_seed(memory.id)).set(topic_data)
