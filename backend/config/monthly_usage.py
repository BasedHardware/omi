"""Shared configuration and schema fields for monthly usage totals."""

import os
import re

FIELDS = ('transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds')


def usage_month_epoch() -> str:
    value = os.environ.get('FSR_USAGE_MONTH_TOTAL_EPOCH', 'v1')
    # Empty/malformed epochs must never accidentally reuse a ready total.
    return value if re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else ''
