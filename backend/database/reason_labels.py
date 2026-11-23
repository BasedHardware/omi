"""Import-light reason families and shared label telemetry below serving callers.

The public observability vocabulary reuses these exact enum/counter objects.
No client, store or caller utility belongs in this dependency core.
"""

from enum import StrEnum

from prometheus_client import Counter


class ReasonFamily(StrEnum):
    AUDIO_RAW = 'audio_raw'
    MEMORY_L1 = 'memory_l1'
    OWNER_RECOGNITION = 'owner_recognition'
    PUSHER_PCM = 'pusher_pcm'
    LIVE_STT = 'live_stt'
    WORKER_VALIDATION = 'worker_validation'
    RECOVERY_FAILURE = 'recovery_failure'
    STALE_RECOVERY = 'stale_recovery'
    RECORDING_ROTATION = 'recording_rotation'
    WORK_OUTCOME = 'work_outcome'
    QUARANTINE = 'quarantine'
    FALLBACK = 'fallback'
    RETRY = 'retry'
    CONSUMER = 'consumer'
    PROVIDER_STT = 'provider_stt'
    RAMP = 'ramp'
    LEGACY_DARK = 'legacy_dark'
    PARITY = 'parity'
    STAGING_FENCE = 'staging_fence'
    HELD_CONTENT = 'held_content'
    SPEAKER_EVIDENCE = 'speaker_evidence'
    NOTES_AGENT_FORCE = 'notes_agent_force'
    NOTES_AGENT_TRANSPORT = 'notes_agent_transport'
    NOTES_QUALITY_REPAIR = 'notes_quality_repair'
    SYNC_DISPATCH = 'sync_dispatch'
    SYNC_CAPTURE_TIME = 'sync_capture_time'
    SYNC_FUTURE_CAPTURE_RECOVERY = 'sync_future_capture_recovery'
    SYNC_BRIDGE_CONTAINMENT = 'sync_bridge_containment'
    SYNC_PROCESSING_HOLD = 'sync_processing_hold'
    APP_REVIEW_CONFIG = 'app_review_config'
    ADMISSION_HOLD = 'admission_hold'
    LISTEN_SESSION_TRANSCRIPT = 'listen_session_transcript'
    RECORD_PARTIAL_RERUN = 'record_partial_rerun'
    VENDOR_ROUTE = 'vendor_route'
    DELIVERY = 'delivery'
    BATCH_FINAL_PASS = 'batch_final_pass'
    RECURRING_VOICE = 'recurring_voice'
    RECORD_GAP_FILL = 'record_gap_fill'
    RECORD_RETAINED_ACK = 'record_retained_ack'
    PIPELINE_LEDGER = 'pipeline_ledger'
    CAPTURE_END = 'capture_end'
    JOURNEY_FAILURE = 'journey_failure'
    LISTEN_NO_AUDIO_CLOSE = 'listen_no_audio_close'
    DUE_MARKER_SWEEP = 'due_marker_sweep'
    SUMMARY_REPAIR_DISCOVERY = 'summary_repair_discovery'
    RECORD_SEAL_REPAIR = 'record_seal_repair'
    HISTORICAL_SUMMARY_OPEN = 'historical_summary_open'


REASON_UNKNOWN_TOTAL = Counter(
    'omi_reason_unknown_total',
    'Values presented to a closed reason enum that were not members, by reason family',
    ['family'],
)


OMI_REASON_TOTAL = Counter(
    'omi_reason_total',
    'Values presented to a closed reason enum (denominator for omi:reason_unknown_ratio:rate30m), by reason family',
    ['family'],
)


for _family in ReasonFamily:  # pre-initialise children so rate() sees them from the first scrape
    REASON_UNKNOWN_TOTAL.labels(family=_family.value)
    OMI_REASON_TOTAL.labels(family=_family.value)


def reason_label(family: ReasonFamily, value: object, enum: type[StrEnum]) -> str:
    """Return ``value`` if it is a member of ``enum``; otherwise count it and return ``'unknown'``.

    Never raises. The family label is bounded by ``ReasonFamily``.
    """
    try:
        family_label = ReasonFamily(family).value
    except Exception:
        family_label = 'unknown'
    result = 'unknown'
    try:
        if isinstance(value, str):
            result = enum(value).value
        elif isinstance(value, enum):
            result = value.value
    except Exception:
        result = 'unknown'
    try:
        OMI_REASON_TOTAL.labels(family=family_label).inc()
        if result == 'unknown' and value != 'unknown':
            REASON_UNKNOWN_TOTAL.labels(family=family_label).inc()
    except Exception:
        pass
    return result
