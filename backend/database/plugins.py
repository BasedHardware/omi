from datetime import datetime, timezone

from models.plugin import UsageHistoryType
from ._client import db


# *****************************
# ********** CRUD *************
# *****************************

def record_plugin_usage(
        uid: str, plugin_id: str, usage_type: UsageHistoryType, memory_id: str = None, message_id: str = None,
        timestamp: datetime = None
):
    if not memory_id and not message_id:
        raise ValueError('memory_id or message_id must be provided')

    data = {
        'uid': uid,
        'memory_id': memory_id,
        'message_id': message_id,
        'timestamp': datetime.now(timezone.utc) if timestamp is None else timestamp,
        'type': usage_type,
    }
    db.collection('plugins').document(plugin_id).collection('usage_history').document(memory_id or message_id).set(data)
    return data


def get_plugin_usage_history(plugin_id: str):
    usage = db.collection('plugins').document(plugin_id).collection('usage_history').stream()
    return [doc.to_dict() for doc in usage]
