import uuid
from datetime import datetime, timezone

from models.plugin import UsageHistoryType
from ._client import db


# *****************************
# ********** CRUD *************
# *****************************

def record_plugin_usage(uid: str, memory_id: str, plugin_id: str, usage_type: UsageHistoryType):
    rid = str(uuid.uuid4())
    data = {
        'id': rid,
        'uid': uid,
        'memory_id': memory_id,
        'timestamp': datetime.now(timezone.utc),
        'type': usage_type,
    }
    db.collection('plugins').document(plugin_id).collection('usage_history').document(rid).set(data)
    return data


def get_plugin_usage_history(plugin_id: str):
    usage = db.collection('plugins').document(plugin_id).collection('usage_history').stream()
    return [doc.to_dict() for doc in usage]
