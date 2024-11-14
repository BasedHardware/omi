import os
from typing import List

from google.cloud.firestore_v1.base_query import BaseCompositeFilter, FieldFilter
from ulid import ULID

from ._client import db

# *****************************
# ********** CRUD *************
# *****************************

omi_plugins_bucket = os.getenv('BUCKET_PLUGINS_LOGOS')


def get_app_by_id_db(app_id: str):
    app_ref = db.collection('plugins_data').document(app_id)
    doc = app_ref.get()
    if doc.exists:
        if doc.to_dict().get('deleted', True):
            return None
        else:
            return doc.to_dict()
    return None


def get_private_apps_db(uid: str) -> List:
    filters = [FieldFilter('uid', '==', uid), FieldFilter('private', '==', True), FieldFilter('deleted', '==', False)]
    private_apps = db.collection('plugins_data').where(filter=BaseCompositeFilter('AND', filters)).stream()
    data = [doc.to_dict() for doc in private_apps]
    return data


# This returns public unapproved apps of all users
def get_unapproved_public_apps_db() -> List:
    filters = [FieldFilter('approved', '==', False), FieldFilter('private', '==', False), FieldFilter('deleted', '==', False)]
    public_apps = db.collection('plugins_data').where(filter=BaseCompositeFilter('AND', filters)).stream()
    return [doc.to_dict() for doc in public_apps]


def get_public_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').stream()
    data = [doc.to_dict() for doc in public_plugins]

    return [plugin for plugin in data if plugin['approved'] == True or plugin['uid'] == uid]


def get_public_approved_apps_db() -> List:
    filters = [FieldFilter('approved', '==', True), FieldFilter('deleted', '==', False)]
    public_apps = db.collection('plugins_data').where(filter=BaseCompositeFilter('AND', filters)).stream()
    return [doc.to_dict() for doc in public_apps]


# This returns public unapproved apps for a user
def get_public_unapproved_apps_db(uid: str) -> List:
    filters = [FieldFilter('approved', '==', False), FieldFilter('uid', '==', uid), FieldFilter('deleted', '==', False), FieldFilter('private', '==', False)]
    public_apps = db.collection('plugins_data').where(filter=BaseCompositeFilter('AND', filters)).stream()
    return [doc.to_dict() for doc in public_apps]


def add_app_to_db(app_data: dict):
    app_ref = db.collection('plugins_data')
    app_ref.add(app_data, app_data['id'])


def update_app_in_db(app_data: dict):
    app_ref = db.collection('plugins_data').document(app_data['id'])
    app_ref.update(app_data)


def delete_app_from_db(app_id: str):
    app_ref = db.collection('plugins_data').document(app_id)
    app_ref.update({'deleted': True})


def update_app_visibility_in_db(app_id: str, private: bool):
    app_ref = db.collection('plugins_data').document(app_id)
    if 'private' in app_id and not private:
        app = app_ref.get().to_dict()
        app_ref.delete()
        new_app_id = app_id.split('-private')[0] + '-' + str(ULID())
        app['id'] = new_app_id
        app['private'] = private
        app_ref = db.collection('plugins_data').document(new_app_id)
        app_ref.set(app)
    else:
        app_ref.update({'private': private})


def change_app_approval_status(plugin_id: str, approved: bool):
    plugin_ref = db.collection('plugins_data').document(plugin_id)
    plugin_ref.update({'approved': approved, 'status': 'approved' if approved else 'rejected'})
