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
    public_plugins = db.collection('plugins_data').where('approved', '==', False).where('private','==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


def get_public_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).where('private','==',False).stream()
    data = [doc.to_dict() for doc in public_plugins]

    # Include the doc if it is not approved but uid matches
    unapproved = db.collection('plugins_data').where('approved', '==', False).where('uid', '==', uid).where('private', '==', False).stream()
    data.extend([doc.to_dict() for doc in unapproved])

    return data


def get_public_approved_apps_db() -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', True).where('deleted', '==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


def get_public_unapproved_apps_db(uid: str) -> List:
    public_plugins = db.collection('plugins_data').where('approved', '==', False).where('uid', '==', uid).where('deleted','==', False).stream()
    return [doc.to_dict() for doc in public_plugins]


# def public_app_id_exists_db(app_id: str) -> bool:
#     app_ref = db.collection('plugins_data').document(app_id)
#     return app_ref.get().exists
#
#
# def private_app_id_exists_db(app_id: str, uid: str) -> bool:
#     app_ref = db.collection('users').document(uid).collection('plugins').document(app_id)
#     return app_ref.get().exists


# def get_incremented_public_app_id(app_id: str):
#     res = db.collection('plugins_data').count().get()
#     apps_count = res[0][0].value
#     return f'{app_id}-{apps_count}'
#
#
# def get_incremented_private_app_id(app_id: str, uid: str):
#     res = db.collection('users').document(uid).collection('plugins').count().get()
#     apps_count = res[0][0].value
#     app_id = app_id.split('-private')[0]
#     return f'{app_id}-{apps_count}-private'


def add_app_to_db(app_data: dict):
    plugin_ref = db.collection('plugins_data')
    plugin_ref.add(app_data, app_data['id'])


def update_app_in_db(app_data: dict):
    plugin_ref = db.collection('plugins_data').document(app_data['id'])
    plugin_ref.update(app_data)


def delete_app_from_db(app_id: str):
    plugin_ref = db.collection('plugins_data').document(app_id)
    plugin_ref.update({'deleted': True})

def update_app_visibility_in_db(app_id: str, private: bool):
    plugin_ref = db.collection('plugins_data').document(app_id)
    plugin_ref.update({'private': private})


def add_public_app(plugin_data: dict):
    plugin_ref = db.collection('plugins_data')
    plugin_ref.add(plugin_data, plugin_data['id'])


def add_private_app(plugin_data: dict, uid: str):
    plugin_ref = db.collection('users').document(uid).collection('plugins')
    plugin_ref.add(plugin_data, plugin_data['id'])


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


# def change_app_visibility_db(app_id: str, private: bool, was_public: bool, uid: str):
#     if was_public and private:  # public -> private
#         plugin_ref = db.collection('plugins_data').document(app_id)
#         plugin = plugin_ref.get().to_dict()
#         plugin_ref.delete()
#         new_plugin_id = f'{app_id}-private'
#         if private_app_id_exists_db(new_plugin_id, uid):
#             new_plugin_id = get_incremented_private_app_id(app_id, uid)
#         plugin['id'] = new_plugin_id
#         plugin['private'] = private
#         plugin_ref = db.collection('users').document(uid).collection('plugins').document(new_plugin_id)
#         plugin_ref.set(plugin)
#     elif not was_public and not private:  # private -> public
#         plugin_ref = db.collection('users').document(uid).collection('plugins').document(app_id)
#         plugin = plugin_ref.get().to_dict()
#         plugin_ref.delete()
#         new_plugin_id = app_id.split('-private')[0]
#         if public_app_id_exists_db(new_plugin_id):
#             new_plugin_id = get_incremented_public_app_id(app_id)
#         plugin['id'] = new_plugin_id
#         plugin['private'] = private
#         if public_app_id_exists_db(new_plugin_id):
#             new_plugin_id = new_plugin_id + '-' + ''.join([str(random.randint(0, 9)) for _ in range(5)])
#         plugin_ref = db.collection('plugins_data').document(new_plugin_id)
#         plugin_ref.set(plugin)
