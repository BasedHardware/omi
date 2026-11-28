# LIFECYCLE: one-time
# DELETE-AFTER: https://github.com/BasedHardware/omi/issues/25578
# RETIRING: legacy sync is dark in production (rollout_cohorts/_ramp legacy_sync=dark);
# the batch pipeline serves every sync upload. Do not add behaviour or route work here.
# Deletion is tracked in SCA-2965; tests/unit/test_sync_legacy_import_ratchet.py freezes it.
"""Persist one encrypted multilingual result before legacy assignment can retry."""

import json
from typing import Any, Callable

from database.sync_empty_recovery import claim, settle
from utils.encryption import decrypt, encrypt


def dispatch_once(uid: str, segment_id: str, dispatch: Callable[[], Any]) -> Any:
    ref, version, cached = claim(uid, segment_id)
    if cached is not None:
        try:
            envelope = json.loads(decrypt(cached, uid))
            response = envelope['response']
            return tuple(response) if envelope['is_tuple'] is True else response
        except Exception:
            raise RuntimeError('sync empty recovery receipt invalid') from None
    response = dispatch()
    # Store the response, including a definitive empty result, before any
    # parsing/assignment. Uncertain calls and lost settle replies never redispatch.
    encoded = encrypt(json.dumps({'response': response, 'is_tuple': isinstance(response, tuple)}, allow_nan=False), uid)
    settle(uid, ref, version, encoded)
    return response
