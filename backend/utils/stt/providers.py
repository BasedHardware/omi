import os
from enum import Enum
from typing import Callable, List, Optional, Protocol, Sequence, Tuple, Union

from models.transcript_segment import ProviderTranscriptResult


class STTProviderName(str, Enum):
    assemblyai = 'assemblyai'
    deepgram = 'deepgram'


class STTWorkload(str, Enum):
    background = 'background'
    postprocess = 'postprocess'
    ptt = 'ptt'
    realtime = 'realtime'
    sync = 'sync'
    voice_message = 'voice_message'


class PrerecordedSTTProvider(Protocol):
    provider_name: STTProviderName

    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: int = None,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        model: str = 'nova-3',
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[ProviderTranscriptResult, Tuple[ProviderTranscriptResult, str]]: ...

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        model: str = 'nova-3',
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[ProviderTranscriptResult, Tuple[ProviderTranscriptResult, str]]: ...


class StreamingSTTProvider(Protocol):
    provider_name: STTProviderName

    async def connect_stream(
        self,
        stream_transcript,
        language: str,
        sample_rate: int,
        channels: int,
        model: str = 'nova-3',
        keywords: List[str] = [],
        vad_gate=None,
        is_active: Optional[Callable[[], bool]] = None,
    ): ...


class DiarizationProvider(Protocol):
    provider_name: STTProviderName


class SpeakerIdentityProvider(Protocol):
    provider_name: str


_DEFAULT_PRERECORDED_WORKLOAD_PROVIDERS = {
    STTWorkload.background: STTProviderName.deepgram,
    STTWorkload.postprocess: STTProviderName.deepgram,
    STTWorkload.ptt: STTProviderName.deepgram,
    STTWorkload.sync: STTProviderName.deepgram,
    STTWorkload.voice_message: STTProviderName.deepgram,
}

_ASSEMBLYAI_ELIGIBLE_WORKLOADS = {
    STTWorkload.background,
    STTWorkload.postprocess,
    STTWorkload.sync,
}

_STREAMING_WORKLOAD_PROVIDERS = {
    STTWorkload.ptt: STTProviderName.deepgram,
    STTWorkload.realtime: STTProviderName.deepgram,
}


def get_prerecorded_provider_name(workload: STTWorkload) -> STTProviderName:
    workload = STTWorkload(workload)
    if _assemblyai_background_enabled() and workload in _assemblyai_enabled_workloads():
        return STTProviderName.assemblyai
    return _DEFAULT_PRERECORDED_WORKLOAD_PROVIDERS[workload]


def get_streaming_provider_name(workload: STTWorkload) -> STTProviderName:
    return _STREAMING_WORKLOAD_PROVIDERS[STTWorkload(workload)]


def get_fallback_prerecorded_provider_name(
    provider: STTProviderName, workload: STTWorkload
) -> Optional[STTProviderName]:
    workload = STTWorkload(workload)
    provider = STTProviderName(provider)
    if workload == STTWorkload.background and provider == STTProviderName.assemblyai:
        return None
    fallback = _DEFAULT_PRERECORDED_WORKLOAD_PROVIDERS[workload]
    if provider != fallback:
        return fallback
    return None


def _assemblyai_background_enabled() -> bool:
    return os.getenv('ASSEMBLYAI_BACKGROUND_STT_ENABLED', 'false').lower() == 'true'


def _assemblyai_enabled_workloads() -> set[STTWorkload]:
    configured = os.getenv('ASSEMBLYAI_BACKGROUND_STT_WORKLOADS', 'sync,background,postprocess')
    workloads = set()
    for raw_value in configured.split(','):
        value = raw_value.strip()
        if not value:
            continue
        try:
            workload = STTWorkload(value)
        except ValueError:
            continue
        if workload in _ASSEMBLYAI_ELIGIBLE_WORKLOADS:
            workloads.add(workload)
    return workloads
