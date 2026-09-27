"""Deterministic pre-recorded STT stub for offline harness sessions.

Mirrors the ``OMI_LLM_STUB`` pattern (``utils.llm.desktop_llm_stub``): an
env-gated in-process stand-in so ``PROVIDER_MODE=offline`` sessions can
complete transcript -> conversation end-to-end without any provider
credential. Without it, an uploaded capture dead-ends at
``PrerecordedSTTConfigurationError`` (the hosted parakeet URL is a provider
secret that offline stages strip by design) and the conversation stays
unfinalized forever.

The stub is double-gated — ``OMI_STT_STUB`` truthy AND an offline provider
stage — and that flag is set only in dev-harness child environments
(``scripts/dev-harness/dev_harness/config.py``). It can never activate in a
production-family process.

Transcripts are deliberately self-declaring synthetic text so harness output
can never be mistaken for real transcription quality — in the app UI or in
session evidence.
"""

import logging
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from utils.stt.pre_recorded import PrerecordedSTTProvider

logger = logging.getLogger(__name__)

_STUB_TEXT = ('[offline', 'stub', 'transcript', '—', 'no', 'real', 'speech', 'recognized]')
_WORD_SPACING_S = 0.6
_WORD_DURATION_S = 0.5


def stub_flag_is_truthy(value: str) -> bool:
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def prerecorded_stub_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    if not stub_flag_is_truthy(env.get('OMI_STT_STUB', '')):
        return False
    stage = env.get('PROVIDER_MODE', '').strip().lower() or env.get('OMI_ENV_STAGE', '').strip().lower()
    return stage == 'offline'


def _stub_words() -> List[Dict[str, Any]]:
    words: List[Dict[str, Any]] = []
    start = 0.0
    for token in _STUB_TEXT:
        words.append(
            {
                'timestamp': (round(start, 2), round(start + _WORD_DURATION_S, 2)),
                'speaker': 'A',
                'text': token,
            }
        )
        start += _WORD_SPACING_S
    return words


class PrerecordedStubProvider(PrerecordedSTTProvider):
    """Deterministic single-speaker transcript; ignores the audio entirely."""

    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: Optional[int] = None,
        attempts: int = 0,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
        logger.info('prerecorded_stub transcribe_url synthetic_transcript=true')
        words = _stub_words()
        return (words, 'en') if return_language else words

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        attempts: int = 0,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
        logger.info('prerecorded_stub transcribe_bytes bytes_len=%s synthetic_transcript=true', len(audio_bytes))
        words = _stub_words()
        return (words, 'en') if return_language else words
