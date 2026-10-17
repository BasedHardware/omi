"""Dark, batch-hash live vendor retirement; final transcript ownership is durable."""

import os

from config.batch_pipeline import in_percent_cohort, record_capture_eligible
from config.live_demand import language_qualified


def selected(uid: str) -> bool:
    try:
        return in_percent_cohort(uid, float(os.getenv('BATCH_LIVE_STT_RETIRE_PERCENT', '0')))
    except ValueError:
        return False


def covered(host) -> bool:
    capture = getattr(host, 'batch_record_capture', None)
    return bool(
        capture
        and capture.get('record_lane_owner') == 'batch_live_v1'
        and capture.get('id') == host.state.current_conversation_id
        and record_capture_eligible(host.request.uid, capture)
        and host.private_cloud_sync_enabled
        and not host.is_multi_channel
        and not host.use_custom_stt
        and not host.request.onboarding_mode
        and host.request.source != 'phone_call'
        and host.pusher_enabled
        and language_qualified(host)
    )
