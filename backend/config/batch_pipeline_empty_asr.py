"""Ship-on protection for speech-bearing empty ASR. Read the kill switch per call."""

import os


def safety_net_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true').strip().lower() != 'false'


def two_recognizer_empty_close_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_TWO_RECOGNIZER_EMPTY_CLOSE_ENABLED', 'false').strip().lower() == 'true'


def two_empty_recognizers(receipts) -> bool:
    """Two distinct recognizers that each returned a validated empty answer."""
    return (
        isinstance(receipts, dict)
        and len(receipts) == 2
        and all(
            isinstance(receipt, dict)
            and receipt.get('provider') == provider
            and receipt.get('outcome') == 'empty'
            and type(receipt.get('word_count')) is int
            and receipt['word_count'] == 0
            for provider, receipt in receipts.items()
        )
    )


def terminal_empty_allowed(spans, *, recognizer_receipts=None) -> bool:
    # A recognizer returning blanks cannot establish that VAD-positive audio is
    # disposable, including sub-second speech. Strict-VAD silence is separate.
    # Two independent recognizers that both return a validated empty answer may,
    # behind their own switch: no automatic step follows that hold, so retaining
    # it only keeps the whole upload unfinished on the phone until it expires.
    return (
        not safety_net_enabled()
        or not spans
        or (two_recognizer_empty_close_enabled() and two_empty_recognizers(recognizer_receipts))
    )
