"""Closed, content-free categories for handled transcription failures."""

from typing import NamedTuple

_TRANSPORT_EXCEPTION_CLASSES = frozenset(
    {
        'ConnectionClosed',
        'ConnectionClosedError',
        'ConnectionClosedOK',
        'ConnectionResetError',
        'ConnectionAbortedError',
        'BrokenPipeError',
        'TimeoutError',
        'OSError',
        'SSLError',
        'gaierror',
        'RuntimeError',
        'TypeError',
        'ValueError',
    }
)


class TransportFailureFields(NamedTuple):
    exception_class: str
    received_close_code: int
    sent_close_code: int
    close_cause: str
    session_age_bucket: str


def frame_close_code(frame: object) -> int:
    """A close frame's wire code, or -1 when no valid frame was observed."""
    code = getattr(frame, 'code', None)
    if not isinstance(code, int) or isinstance(code, bool):
        return -1
    normalized_code = int(code)
    return normalized_code if 1000 <= normalized_code <= 4999 else -1


def session_age_bucket(age_seconds: float) -> str:
    for limit, bucket in ((30, 'lt_30s'), (300, 'lt_5m'), (1800, 'lt_30m'), (3600, 'lt_60m'), (18000, 'lt_300m')):
        if age_seconds < limit:
            return bucket
    return 'ge_300m'


def transport_failure_fields(error: BaseException, age_seconds: float) -> TransportFailureFields:
    """Never serialize exception text, close reasons, or arbitrary class names.

    Separate received/sent codes distinguish a remote close from our own 1011
    keepalive timeout. -1 means no close frame was observed in that direction.
    """

    received = getattr(error, 'rcvd', None)
    sent = getattr(error, 'sent', None)
    name = type(error).__name__
    return TransportFailureFields(
        name if name in _TRANSPORT_EXCEPTION_CLASSES else 'other',
        frame_close_code(received),
        frame_close_code(sent),
        'keepalive_ping_timeout' if getattr(sent, 'reason', None) == 'keepalive ping timeout' else 'other',
        session_age_bucket(age_seconds),
    )


# Content-free cause behind an otherwise untyped connection_lost death.
CONNECTION_LOSS_CAUSES = frozenset(
    {
        'remote_close_normal',
        'remote_close_error',
        'keepalive_timeout',
        'abnormal_close',
        'clean_eof',
        'reset',
        'timeout',
        'tls',
        'dns',
        'other',
    }
)


def connection_loss_cause(error: BaseException) -> str:
    """Bucket a transport exception by close frames and class, never by text."""
    code = getattr(getattr(error, 'rcvd', None), 'code', None)
    if isinstance(code, int) and not isinstance(code, bool):
        return 'remote_close_normal' if code in (1000, 1001) else 'remote_close_error'
    if getattr(getattr(error, 'sent', None), 'reason', None) == 'keepalive ping timeout':
        return 'keepalive_timeout'
    name = type(error).__name__
    if name.startswith('ConnectionClosed'):
        return 'abnormal_close'
    if name in {'ConnectionResetError', 'ConnectionAbortedError', 'BrokenPipeError'}:
        return 'reset'
    if name == 'TimeoutError':
        return 'timeout'
    if name.startswith('SSL'):
        return 'tls'
    if name == 'gaierror':
        return 'dns'
    return 'other'


_STAGES = {
    '_save_wav': 'upload_save',
    '_prepare_voice_message_url': 'storage_prepare',
    'get_syncing_file_temporal_signed_url': 'storage_prepare',
    '_get_signed_url': 'storage_sign',
    'iam_signing_kwargs': 'storage_sign',
    '_validated_wav_is_silent': 'audio_decode',
    '_run_file_vad': 'audio_decode',
    '_segments_from_16khz_samples': 'vad_inference',
    '_get_ort_session': 'vad_inference',
    'get_prerecorded_provider': 'provider_selection',
    'parakeet_prerecorded': 'provider_download',
    '_normalize_parakeet_download': 'provider_decode',
    'parakeet_prerecorded_from_bytes': 'provider_request',
    'postprocess_words': 'transcript_processing',
}
_ERROR_KINDS = {
    'FileNotFoundError': 'file_missing',
    'PermissionError': 'permission',
    'CouldntDecodeError': 'audio_decode',
    'VADAudioDecodeError': 'audio_decode',
    'ParakeetAudioDecodeError': 'audio_decode',
    'VADProcessingError': 'vad_processing',
    'TypeError': 'type',
    'ValueError': 'value',
    'AttributeError': 'attribute',
    'TimeoutError': 'timeout',
    'ReadTimeout': 'timeout',
    'ConnectTimeout': 'timeout',
    'HTTPStatusError': 'upstream_http',
    'Forbidden': 'permission',
    'RefreshError': 'credential_refresh',
    'TransportError': 'transport',
}


def transcription_failure_categories(error: BaseException) -> tuple[str, str]:
    """Inspect bounded traceback/cause shapes, never messages or frame values."""
    stage, kind = 'unknown', 'other'
    seen: set[int] = set()
    current: BaseException | None = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        kind = _ERROR_KINDS.get(type(current).__name__, 'other')
        trace = current.__traceback__
        for _ in range(32):
            if trace is None:
                break
            stage = _STAGES.get(trace.tb_frame.f_code.co_name, stage)
            trace = trace.tb_next
        current = current.__cause__ or current.__context__
    return stage, kind
