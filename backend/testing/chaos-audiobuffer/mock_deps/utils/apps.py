"""Mock utils.apps — audio bytes apps disabled for audiobuffer leak repro."""


def is_audio_bytes_app_enabled(uid):
    return False
