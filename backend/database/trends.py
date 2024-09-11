from datetime import datetime
from typing import Dict, List

from google.api_core.retry import Retry
from google.cloud.firestore_v1 import FieldFilter

from models.memory import Memory
from models.trend import Trend
from ._client import db


def get_trends_data() -> List[Dict[str, Trend]]:
    trends_ref = db.collection('trends')
    trends_docs = [doc for doc in trends_ref.stream(retry=Retry())]
    trends_list = []
    for doc in trends_docs:
        trend = doc.to_dict()
        trend['id'] = doc.id
        trend['name'] = trend['name']
        trend['created_at'] = str(trend['created_at'])
        data = doc.reference.collection('data').count().get()[0][0].value
        trend['data'] = data
        trends_list.append({trend['name']: trend})
        print(f"{{'{trend['name']}' : {trend}}}")
    return trends_list


def save_trends(memory: Memory, trends: List[str]):
    mem_data = {
        'date': memory.created_at,
        'memory_id': memory.id
    }
    print(f"trend_data: {mem_data}")
    trends_ref = db.collection('trends')
    for trend in trends:
        trend_ref = trends_ref.where(filter=FieldFilter('name', '==', trend)).get()
        if len(trend_ref) == 0:
            trends_ref.add({"created_at": datetime.now(), "name": trend})
            trend_ref = trends_ref.where(filter=FieldFilter('name', '==', trend)).get()
        trend_ref[0].reference.collection('data').add(mem_data)
