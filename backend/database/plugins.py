import os
from datetime import datetime, timezone
from typing import List

import requests

from models.plugin import UsageHistoryType
from utils.other.storage import storage_client
from ._client import db

# *****************************
# ********** CRUD *************
# *****************************

omi_plugins_bucket = os.getenv('BUCKET_PLUGINS_LOGOS')


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


def add_plugin_from_community_json(plugin_data: dict):
    img = requests.get("https://raw.githubusercontent.com/BasedHardware/Omi/main/" + plugin_data['image'], stream=True)
    bucket = storage_client.bucket(omi_plugins_bucket)
    path = plugin_data['image'].split('/plugins/logos/')[1]
    blob = bucket.blob(path)
    blob.upload_from_file(img.raw)
    plugin_data['image'] = f'https://storage.googleapis.com/{omi_plugins_bucket}/{path}'
    plugin_data['private'] = False
    plugin_data['approved'] = True
    plugin_data['status'] = 'approved'
    if "external_integration" in plugin_data['capabilities']:
        plugin_data['external_integration'][
            'setup_instructions_file_path'] = "https://raw.githubusercontent.com/BasedHardware/Omi/main/" + \
                                              plugin_data['external_integration']['setup_instructions_file_path']
    plugin_ref = db.collection('plugins_data').document(plugin_data['id'])
    if plugin_ref.get().exists:
        plugin_ref.update(plugin_data)
    else:
        plugin_ref.set(plugin_data)
