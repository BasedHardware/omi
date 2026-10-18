"""Persist one encrypted multilingual result before legacy assignment can retry."""

import json

from database.sync_empty_recovery import claim, settle
from utils.encryption import decrypt, encrypt


def dispatch_once(uid, segment_id, dispatch):
    ref, version, cached = claim(uid, segment_id)
    if cached is not None:
        words, language = json.loads(decrypt(cached, uid))
        return words, language
    response = dispatch()
    # Store the response, including a definitive empty result, before any
    # parsing/assignment. Uncertain calls and lost settle replies never redispatch.
    encoded = encrypt(json.dumps(response, allow_nan=False), uid)
    settle(uid, ref, version, encoded)
    return response
