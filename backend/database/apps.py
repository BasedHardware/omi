import os
import random
from datetime import datetime, timezone
from typing import List

import requests

from models.app import App
from models.plugin import UsageHistoryType
from utils.other.storage import storage_client
from ._client import db

# *****************************
# ********** CRUD *************
# *****************************

omi_plugins_bucket = os.getenv('BUCKET_PLUGINS_LOGOS')


def get_app_by_id_db(plugin_id: str, uid: str):
    if 'private' in plugin_id:
        plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
    else:
        plugin_ref = db.collection('plugins_data').document(plugin_id)
    return plugin_ref.get().to_dict()

def get_private_apps_db(uid: str) -> List:
    private_plugins = db.collection('users').document(uid).collection('plugins').stream()
    data = [doc.to_dict() for doc in private_plugins]
    return data


def get_unapproved_public_apps_db() -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


def get_public_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).stream()
    data = [doc.to_dict() for doc in public_plugins]

    # Include the doc if it is not approved but uid matches
    unapproved = db.collection('plugins_data').where('approved', '==', False).where('uid', '==', uid).stream()
    data.extend([doc.to_dict() for doc in unapproved])

    return data


def get_public_approved_apps_db() -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).stream()
    return [doc.to_dict() for doc in public_plugins]


def get_public_unapproved_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', False).where('uid', '==', uid).stream()
    return [doc.to_dict() for doc in public_plugins]


def public_app_id_exists_db(app_id: str) -> bool:
    app_ref = db.collection('plugins_data').document(app_id)
    return app_ref.get().exists


def private_app_id_exists_db(app_id: str, uid: str) -> bool:
    app_ref = db.collection('users').document(uid).collection('plugins').document(app_id)
    return app_ref.get().exists


def add_public_app(plugin_data: dict):
    plugin_ref = db.collection('plugins_data')
    plugin_ref.add(plugin_data, plugin_data['id'])


def add_private_app(plugin_data: dict, uid: str):
    plugin_ref = db.collection('users').document(uid).collection('plugins')
    plugin_ref.add(plugin_data, plugin_data['id'])


def get_app_by_id_db(plugin_id: str, uid: str):
    if 'private' in plugin_id:
        plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
    else:
        plugin_ref = db.collection('plugins_data').document(plugin_id)
    return plugin_ref.get().to_dict()


def update_public_app(plugin_data: dict):
    plugin_ref = db.collection('plugins_data').document(plugin_data['id'])
    plugin_ref.update(plugin_data)


def update_private_app(plugin_data: dict, uid: str):
    plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_data['id'])
    plugin_ref.update(plugin_data)


def delete_private_app(plugin_id: str, uid: str):
    plugin_ref = db.collection('users').document(uid).collection('plugins').document(plugin_id)
    plugin_ref.update({'deleted': True})


def delete_public_app(plugin_id: str):
    plugin_ref = db.collection('plugins_data').document(plugin_id)
    plugin_ref.update({'deleted': True})


def change_app_approval_status(plugin_id: str, approved: bool):
    plugin_ref = db.collection('plugins_data').document(plugin_id)
    plugin_ref.update({'approved': approved, 'status': 'approved' if approved else 'rejected'})
