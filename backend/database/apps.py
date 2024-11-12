import os
from typing import List

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
        return doc.to_dict()
    return None


def get_private_apps_db(uid: str) -> List:
    private_plugins = db.collection('plugins_data').where('uid', '==', uid).where('private', '==', True).stream()
    data = [doc.to_dict() for doc in private_plugins]
    return data


def get_unapproved_public_apps_db() -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', False).where('private', '==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


def get_public_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).where('private', '==', False).stream()
    data = [doc.to_dict() for doc in public_plugins]

    # Include the doc if it is not approved but uid matches
    unapproved = db.collection('plugins_data').where('approved', '==', False).where('uid', '==', uid).where('private',
                                                                                                            '==',
                                                                                                            False).stream()
    data.extend([doc.to_dict() for doc in unapproved])

    return data


def get_public_approved_apps_db() -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).where('deleted', '==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


def get_public_unapproved_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', False).where('uid', '==', uid).where(
        'deleted', '==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


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
    app_ref.update({'private': private})


def change_app_approval_status(plugin_id: str, approved: bool):
    plugin_ref = db.collection('plugins_data').document(plugin_id)
    plugin_ref.update({'approved': approved, 'status': 'approved' if approved else 'rejected'})

