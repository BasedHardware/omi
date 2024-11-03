from datetime import datetime, timezone
from typing import List

import requests

from models.plugin import UsageHistoryType
from utils.other.storage import storage_client
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


def get_plugin_by_id_db(plugin_id: str, uid: str = None):
    if 'private' in plugin_id:
        plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
    else:
        plugin_ref = db.collection('plugins_data').document(plugin_id)
    return plugin_ref.get().to_dict()


def add_public_plugin(plugin_data: dict):
    plugin_ref = db.collection('plugins_data')
    plugin_ref.add(plugin_data, plugin_data['id'])


def add_private_plugin(plugin_data: dict, uid: str):
    plugin_ref = db.collection('users').document(uid).collection('plugins')
    plugin_ref.add(plugin_data, plugin_data['id'])


def change_plugin_approval_status(plugin_id: str, approved: bool):
    plugin_ref = db.collection('plugins_data').document(plugin_id)
    plugin_ref.update({'approved': approved})


def change_plugin_visibility_db(plugin_id: str, private: bool, was_public: bool, uid: str):
    if was_public and private:   # public -> private
        plugin_ref = db.collection('plugins_data').document(plugin_id)
        plugin = plugin_ref.get().to_dict()
        plugin_ref.delete()
        plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
        plugin['private'] = private
        plugin_ref.set(plugin)
    elif not was_public and not private:    # private -> public
        plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
        plugin = plugin_ref.get().to_dict()
        plugin_ref.delete()
        plugin_ref = db.collection('plugins_data').document(plugin_id)
        plugin_ref.set(plugin)
    else:  # private -> private or public -> public
        plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
        plugin_ref.update({'private': private})


def get_private_plugins_db(uid: str) -> List:
    private_plugins = db.collection('users').document(uid).collection('plugins').stream()
    data = [doc.to_dict() for doc in private_plugins]
    return data

def get_public_plugins_db() -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).stream()
    data = [doc.to_dict() for doc in public_plugins]
    return data


def plugin_id_exists_db(plugin_id: str) -> bool:
    plugin_ref = db.collection('plugins_data').document(plugin_id)
    return plugin_ref.get().exists


# TODO: only temporary, to move from the json file to firestore. Remove after the migration
def add_plugin_script(plugin_data: dict):
    img = requests.get("https://raw.githubusercontent.com/BasedHardware/Omi/main/" + plugin_data['image'], stream=True)
    bucket = storage_client.bucket('omi_plugins')
    path = plugin_data['image'].split('/plugins/logos/')[1]
    blob = bucket.blob(path)
    blob.upload_from_file(img.raw)
    plugin_data['image'] = f'https://storage.googleapis.com/omi_plugins/{path}'
    plugin_data['private'] = False
    plugin_data['approved'] = True

    if "external_integration" in plugin_data['capabilities']:
        plugin_data['external_integration'][
            'setup_instructions_file_path'] = "https://raw.githubusercontent.com/BasedHardware/Omi/main/" + \
                                              plugin_data['external_integration']['setup_instructions_file_path']
    plugin_ref = db.collection('plugins_data').document(plugin_data['id'])
    if plugin_ref.get().exists:
        plugin_ref.update(plugin_data)
    else:
        plugin_ref.set(plugin_data)
