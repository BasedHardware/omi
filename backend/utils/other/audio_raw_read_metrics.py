"""Closed raw-read outcomes; never include capture identity or exception text."""

import logging

from google.cloud.exceptions import NotFound
from prometheus_client import Counter

logger = logging.getLogger(__name__)
RESULTS = frozenset(
    {
        'ok',
        'coverage_mismatch',
        'checksum_mismatch',
        'decode_error',
        'decrypt_error',
        'identity_mismatch',
        'no_pack',
        'other',
    }
)
CODECS = frozenset({'opus', 'flac', 'pcm16', 'pcm8'})
RAW_READ = Counter('omi_audio_raw_read_total', 'Raw audio read outcomes', ['result'])
for _result in RESULTS:
    RAW_READ.labels(result=_result)


class CoverageMismatch(ValueError):
    pass


class ChecksumMismatch(ValueError):
    pass


class DecodeError(ValueError):
    pass


class DecryptError(ValueError):
    pass


def error_result(error: Exception) -> str:
    results: dict[type[Exception], str] = {
        CoverageMismatch: 'coverage_mismatch',
        ChecksumMismatch: 'checksum_mismatch',
        DecodeError: 'decode_error',
        DecryptError: 'decrypt_error',
        NotFound: 'no_pack',
    }
    return results.get(type(error), 'other')


def record(result: str, codec: str | None = None) -> None:
    result = result if result in RESULTS else 'other'
    RAW_READ.labels(result=result).inc()
    if result != 'ok':
        log_failure(result, codec)


def log_failure(result: str, codec: str | None = None) -> None:
    logger.warning(
        'event=audio_raw_read result=%s codec=%s',
        result if result in RESULTS else 'other',
        codec if codec in CODECS else 'other',
    )
