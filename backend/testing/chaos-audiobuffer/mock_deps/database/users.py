"""Mock database.users — disable private cloud sync for audiobuffer leak repro."""


def get_user_private_cloud_sync_enabled(uid):
    return False
