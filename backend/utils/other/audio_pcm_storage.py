"""Optional lossless representation for new custody PCM; never a retention policy."""

import os
import subprocess
import threading
import time

from prometheus_client import Counter, Histogram

from utils.observability.fallback import record_fallback

DECISIONS = Counter('omi_audio_pcm_storage_total', 'New PCM representation attempts', ['result'])
INPUT_BYTES = Counter(
    'omi_audio_pcm_storage_input_bytes_total', 'PCM bytes admitted to encoding attempts, including retries'
)
SAVED_BYTES = Counter('omi_audio_pcm_storage_saved_bytes_total', 'Bytes saved by verified encoding attempts')
STORAGE_SECONDS = Histogram(
    'omi_audio_pcm_storage_seconds',
    'Optional PCM representation time before immutable custody commit, including fallback',
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 5),
)
for _result in ('disabled', 'ineligible', 'busy', 'deadline', 'not_smaller', 'encoder_error', 'mismatch', 'flac'):
    # Expose the bounded outcome children for baseline scrapes. The canary
    # also checks absolute mismatch counts to catch errors before first scrape.
    DECISIONS.labels(_result).inc(0)

# Diagnostics only: these split the optional step into its two children so a
# latency question can be answered without guessing. They never feed the
# p99 guard, which stays on STORAGE_SECONDS above, and they are not a bound.
# `child_result` is that child's own outcome, not the call's final decision.
STAGE_SECONDS = Histogram(
    'omi_audio_pcm_storage_stage_seconds',
    'Wall time of one optional codec child that actually ran, by stage and child outcome',
    ['stage', 'child_result'],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
# Only for a child killed by its own timeout: full stage wall time beyond the
# granted timeout. That span is startup, cleanup, and any descheduling, so this
# is a diagnostic of overshoot, never a pure startup cost or a wall-clock bound.
STAGE_TIMEOUT_OVERSHOOT_SECONDS = Histogram(
    'omi_audio_pcm_storage_stage_timeout_overshoot_seconds',
    'Timed-out child wall time beyond its granted timeout, by stage',
    ['stage'],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
for _stage in ('encode', 'decode'):
    for _child_result in ('success', 'timeout', 'error'):
        # Pre-created so increase() sees a first burst; never observed at zero,
        # because that would fabricate a sample. Eight children: at most 96 new
        # series per pod with buckets, +Inf, _sum, _count and _created.
        STAGE_SECONDS.labels(stage=_stage, child_result=_child_result)
    STAGE_TIMEOUT_OVERSHOOT_SECONDS.labels(stage=_stage)

# One codec child per process. Two children share one vCPU on the pusher pod and
# doubled every call's wall time, which is what broke the 0.5 s p99 guard there;
# a single slot gives the running child the whole slice and reports the rest busy.
_ENCODERS = threading.BoundedSemaphore(1)
_TIMEOUT_SECONDS = 2
# Whole optional step, under the 0.5 s p99 rollback trigger. A pack that cannot
# finish encode+decode inside this budget keeps PCM instead of exceeding the guard.
_TOTAL_BUDGET_SECONDS = 0.4
# FLAC decode is far cheaper than encode; reserve a slice so a successful encode
# still has time to be verified instead of being discarded for lack of budget.
_DECODE_RESERVE_SECONDS = 0.08
_MIN_BYTES = 32000
_MAX_BYTES = 16 * 1024 * 1024


def _stage_timeout(deadline: float, reserve: float = 0.0) -> float:
    """Per-subprocess cap shrunk to what the shared optional budget still allows."""
    return min(_TIMEOUT_SECONDS, deadline - time.monotonic() - reserve)


@STORAGE_SECONDS.time()
def compact_pcm(pcm: bytes, sample_rate: int, channels: int) -> tuple[bytes, str]:
    """Return FLAC only when smaller and independently decoded byte-for-byte.

    Existing FLAC readers need no new container/version. Missing ffmpeg, busy
    workers, timeouts, codec errors and incompressible data all retain PCM.
    Limits bound optional work before the existing durable commit barrier: one
    codec child per process and a shared wall-clock budget for encode+decode, so
    a pack that cannot finish in time keeps PCM instead of delaying custody.
    """
    result = 'disabled'
    payload, codec = pcm, 'pcm16'
    samples = None
    if os.getenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'true').strip().lower() != 'true':
        DECISIONS.labels(result).inc()
        return payload, codec
    if not (_MIN_BYTES <= len(pcm) <= _MAX_BYTES) or channels != 1 or len(pcm) % 2:
        result = 'ineligible'
    elif not _ENCODERS.acquire(blocking=False):
        result = 'busy'
    else:
        # Allocated only once a child can run, so the disabled/ineligible/busy
        # paths keep their current cost. At most two entries, flushed at the tail.
        samples = []
        try:
            INPUT_BYTES.inc(len(pcm))
            deadline = time.monotonic() + _TOTAL_BUDGET_SECONDS
            common = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-threads', '1']
            encode_timeout = _stage_timeout(deadline, _DECODE_RESERVE_SECONDS)
            encoded = None
            if encode_timeout <= 0:
                result = 'deadline'
            else:
                # Timed around the child only; the granted timeout is already
                # decided above, so this read cannot change it.
                encode_started = time.monotonic()
                encode_outcome = 'success'
                try:
                    encoded = subprocess.run(
                        common
                        + [
                            '-f',
                            's16le',
                            '-ar',
                            str(sample_rate),
                            '-ac',
                            '1',
                            '-i',
                            'pipe:0',
                            '-map_metadata',
                            '-1',
                            '-fflags',
                            '+bitexact',
                            '-flags:a',
                            '+bitexact',
                            '-c:a',
                            'flac',
                            '-compression_level',
                            '0',
                            '-threads',
                            '1',
                            '-f',
                            'flac',
                            'pipe:1',
                        ],
                        input=pcm,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        check=True,
                        timeout=encode_timeout,
                    ).stdout
                except subprocess.TimeoutExpired:
                    # A child killed by our own budget is a deadline, not a codec fault.
                    encode_elapsed = time.monotonic() - encode_started
                    encode_outcome = 'timeout'
                    result = 'deadline' if encode_timeout < _TIMEOUT_SECONDS else 'encoder_error'
                except (OSError, subprocess.SubprocessError):
                    encode_elapsed = time.monotonic() - encode_started
                    encode_outcome = 'error'
                    result = 'encoder_error'
                else:
                    # Stop the stage clock as the child returns: nothing after this
                    # point belongs to the child's stage.
                    encode_elapsed = time.monotonic() - encode_started
                samples.append(('encode', encode_elapsed, encode_outcome, encode_timeout))
            if encoded is not None:
                result = 'not_smaller'
                if encoded and len(encoded) * 100 <= len(pcm) * 95:
                    decode_timeout = _stage_timeout(deadline)
                    if decode_timeout <= 0:
                        result = 'deadline'
                    else:
                        decode_started = time.monotonic()
                        decode_outcome = 'success'
                        try:
                            decoded = subprocess.run(
                                common + ['-f', 'flac', '-i', 'pipe:0', '-f', 's16le', '-c:a', 'pcm_s16le', 'pipe:1'],
                                input=encoded,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                check=True,
                                timeout=decode_timeout,
                            ).stdout
                        except subprocess.TimeoutExpired:
                            decode_elapsed = time.monotonic() - decode_started
                            decode_outcome = 'timeout'
                            result = 'deadline' if decode_timeout < _TIMEOUT_SECONDS else 'encoder_error'
                        except (OSError, subprocess.SubprocessError):
                            decode_elapsed = time.monotonic() - decode_started
                            decode_outcome = 'error'
                            result = 'encoder_error'
                        else:
                            # Stop the stage clock as the child returns, before the byte
                            # comparison and saved-byte accounting that follow it.
                            decode_elapsed = time.monotonic() - decode_started
                            result = 'mismatch'
                            if decoded == pcm:
                                payload, codec, result = encoded, 'flac', 'flac'
                                SAVED_BYTES.inc(len(pcm) - len(encoded))
                        samples.append(('decode', decode_elapsed, decode_outcome, decode_timeout))
        finally:
            _ENCODERS.release()
    # Flushed only after the codec slot is released, so the observations stay out
    # of the subprocess and deadline sequence.
    for stage, elapsed, child_result, granted in samples or ():
        STAGE_SECONDS.labels(stage=stage, child_result=child_result).observe(elapsed)
        if child_result == 'timeout':
            STAGE_TIMEOUT_OVERSHOOT_SECONDS.labels(stage=stage).observe(max(0.0, elapsed - granted))
    if result == 'deadline':
        # Shared resilience telemetry: the optional representation was skipped and
        # custody continues with original PCM. The domain counter below stays.
        record_fallback(
            component='audio_custody',
            from_mode='flac',
            to_mode='pcm16',
            reason='timeout',
            outcome='degraded',
        )
    DECISIONS.labels(result).inc()
    return payload, codec
