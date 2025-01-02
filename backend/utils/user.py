from database.apps import batch_update_creator_profile_for_apps_db
from database.users import get_user_creator_profile_db, set_user_creator_profile_db


def get_user_creator_profile(uid: str):
    return get_user_creator_profile_db(uid)


def update_user_creator_profile(uid: str, data: dict):
    return set_user_creator_profile_db(uid, data)


def update_creator_details_for_user_apps(uid: str, data: dict):
    return batch_update_creator_profile_for_apps_db(uid, data['creator_name'], data['creator_email'])


def create_user_creator_profile(uid: str, data: dict):
    return set_user_creator_profile_db(uid, data)
