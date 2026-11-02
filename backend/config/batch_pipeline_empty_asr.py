"""Ship-on protection for speech-bearing empty ASR. Read the kill switch per call."""

import os


def safety_net_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true').strip().lower() != 'false'


def terminal_empty_allowed(spans) -> bool:
    # A recognizer returning blanks cannot establish that VAD-positive audio is
    # disposable, including sub-second speech. Strict-VAD silence is separate.
    return not safety_net_enabled() or not spans
