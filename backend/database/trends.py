from datetime import datetime
from typing import Dict, List

from google.api_core.retry import Retry
from google.cloud.firestore_v1 import FieldFilter

from models.trend import Trend

from ._client import db


def get_trends_data() -> List[Dict[str, Trend]]:
    trends_ref = db.collection('trends')
    trends_docs = [doc for doc in trends_ref.stream(retry=Retry())]
    if len(trends_docs) > 0:
        trends_list = []
        for doc in trends_docs:
            trend = doc.to_dict()
            trend['id'] = doc.id
            trend['name'] = trend['name']
            trend['created_date'] = str(trend['created_date'])
            data = doc.reference.collection('data').count().get()[0][0].value
            trend['data'] = data
            trends_list.append({trend['name']: trend})
            print(f"{{'{trend['name']}' : {trend}}}")
        return trends_list
    return None
