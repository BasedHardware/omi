from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

MAX_CONVERSATION_TIMEOUT_SECONDS = 4 * 60 * 60
MIN_CONVERSATION_TIMEOUT_SECONDS = 120
TARGET_SAMPLE_RATE = 16000
USER_SELF_PERSON_ID = 'user'

# Live-session sources whose devices natively produce photos. Receiving a photo
# must not overwrite their provenance; for every other source the legacy
# behavior stands: a photo-bearing conversation is relabeled 'openglass'.
PHOTO_CAPABLE_SOURCE_VALUES = frozenset({'openglass', 'rayban_meta'})


def resolve_photo_conversation_source(current_source_value: Optional[str]) -> Optional[str]:
    """Source a conversation should carry once it has photos.

    Returns the new source value, or None when the current source already
    identifies a photo-capable device and must be preserved.
    """
    if current_source_value in PHOTO_CAPABLE_SOURCE_VALUES:
        return None
    return 'openglass'


class ConversationLifecycleAction(str, Enum):
    continue_current = 'continue_current'
    create_new = 'create_new'
    process_and_create_new = 'process_and_create_new'


@dataclass(frozen=True)
class CodecFrameDecision:
    codec: str
    frame_size: int
    lc3_chunk_size: Optional[int]
    lc3_frame_duration_us: Optional[int]


@dataclass(frozen=True)
class SttBufferFlushDecision:
    should_flush: bool
    socket_dead: bool
    send_to_stt: bool
    dg_usage_ms: int


@dataclass(frozen=True)
class MultiChannelMixDecision:
    should_mix: bool
    min_len: int


@dataclass(frozen=True)
class SpeakerTextAssignmentDecision:
    person_id: Optional[str]
    should_create_person: bool
    event_person_id: str
    update_maps: bool


def should_include_speech_profile(include_speech_profile: bool, is_multi_channel: bool, onboarding_mode: bool) -> bool:
    if is_multi_channel or onboarding_mode:
        return False
    return include_speech_profile


def normalize_codec_frame(codec: str) -> CodecFrameDecision:
    frame_size = 160
    lc3_chunk_size = None
    lc3_frame_duration_us = None

    if codec == 'opus_fs320':
        return CodecFrameDecision('opus', 320, lc3_chunk_size, lc3_frame_duration_us)
    if codec == 'lc3_fs1030':
        return CodecFrameDecision('lc3', frame_size, 30, 10000)
    return CodecFrameDecision(codec, frame_size, lc3_chunk_size, lc3_frame_duration_us)


OPUS_SUPPORTED_SAMPLE_RATES = frozenset({8000, 12000, 16000, 24000, 48000})


def validate_audio_format(codec: str, sample_rate: int) -> Optional[str]:
    """Reason the client codec/sample_rate cannot initialize a decoder, or None if it can.

    opuslib.Decoder only accepts the standard opus sample rates, and lc3py.Decoder needs a frame
    duration that only the lc3_fs1030 variant carries (bare 'lc3' normalizes to a None duration).
    Checked before any decoder is constructed so an unsupported request closes the socket cleanly
    instead of raising OpusError/TypeError out of the ASGI handler as an unclean 1006 drop.
    """
    if codec in ('opus', 'opus_fs320') and sample_rate not in OPUS_SUPPORTED_SAMPLE_RATES:
        return f'opus requires a sample rate in {sorted(OPUS_SUPPORTED_SAMPLE_RATES)}, got {sample_rate}'
    if codec == 'lc3':
        return 'lc3 streaming requires the lc3_fs1030 codec (bare lc3 has no frame duration)'
    return None


def normalize_language(language: str) -> str:
    return 'multi' if language == 'auto' else language


# STT sentinels meaning "detect the language" — not BCP47 codes, so they can never
# be a translation target (NLLB rejects them as unsupported_target).
LANGUAGE_SENTINELS = frozenset({'multi', 'auto'})


def is_translation_target(language: str) -> bool:
    return bool(language) and language not in LANGUAGE_SENTINELS


def should_force_single_language(onboarding_mode: bool, single_language_mode: bool) -> bool:
    if onboarding_mode:
        return True
    return single_language_mode


def select_translation_language(
    *,
    single_language_mode: bool,
    stt_language: str,
    language: str,
    user_language_preference: str,
) -> Optional[str]:
    if single_language_mode:
        return None
    if stt_language == 'multi':
        if language == 'multi':
            if is_translation_target(user_language_preference):
                return user_language_preference
        elif is_translation_target(language):
            return language
    return None


def effective_conversation_timeout(conversation_timeout: int, is_multi_channel: bool) -> int:
    timeout = conversation_timeout
    if timeout == -1 or is_multi_channel:
        timeout = MAX_CONVERSATION_TIMEOUT_SECONDS
    if timeout < MIN_CONVERSATION_TIMEOUT_SECONDS:
        timeout = MIN_CONVERSATION_TIMEOUT_SECONDS
    return timeout


def should_load_speech_profile(*, use_custom_stt: bool, is_multi_channel: bool, include_speech_profile: bool) -> bool:
    return not use_custom_stt and not is_multi_channel and include_speech_profile


def should_enable_speaker_identification(
    *,
    use_custom_stt: bool,
    private_cloud_sync_enabled: bool,
    has_speech_profile: bool,
) -> bool:
    return not use_custom_stt and (private_cloud_sync_enabled or has_speech_profile)


def decide_existing_conversation_action(
    *, seconds_since_last_segment: float, conversation_creation_timeout: int
) -> ConversationLifecycleAction:
    if seconds_since_last_segment >= conversation_creation_timeout:
        return ConversationLifecycleAction.process_and_create_new
    return ConversationLifecycleAction.continue_current


def decide_lifecycle_action(
    *,
    conversation_exists: bool,
    status: Any,
    in_progress_status: Any,
    seconds_since_last_update: Optional[float],
    conversation_creation_timeout: int,
) -> ConversationLifecycleAction:
    if not conversation_exists:
        return ConversationLifecycleAction.create_new
    if status != in_progress_status:
        return ConversationLifecycleAction.create_new
    if seconds_since_last_update is not None and seconds_since_last_update >= conversation_creation_timeout:
        return ConversationLifecycleAction.process_and_create_new
    return ConversationLifecycleAction.continue_current


def should_process_on_disconnect(
    *,
    is_multi_channel: bool,
    close_code: int,
    conversation_id: Optional[str],
    conversation: Mapping[str, Any],
    in_progress_status: Any,
) -> bool:
    if close_code != 1000:
        return False
    if is_multi_channel or not conversation_id or not conversation:
        return False
    if conversation.get('status') != in_progress_status:
        return False
    if getattr(conversation.get('source'), 'value', conversation.get('source')) != 'desktop':
        return False
    return bool(conversation.get('transcript_segments') or conversation.get('photos'))


def should_remove_in_progress_pointer(*, current_in_progress_id: Optional[str], conversation_id: Optional[str]) -> bool:
    return bool(conversation_id) and current_in_progress_id == conversation_id


def person_id_for_client(person_id: Optional[str], speaker_auto_assign_enabled: bool) -> str:
    if speaker_auto_assign_enabled and person_id:
        return person_id
    return ''


def should_initialize_vad_gate(*, override: Optional[str], global_gate_enabled: bool) -> bool:
    gate_enabled_by_override = override == 'enabled'
    gate_disabled_by_override = override == 'disabled'
    return not gate_disabled_by_override and (global_gate_enabled or gate_enabled_by_override)


def vad_gate_mode(*, override: Optional[str], default_mode: str) -> str:
    return 'active' if override == 'enabled' else default_mode


def stt_buffer_flush_size(sample_rate: int) -> int:
    return int(sample_rate * 2 * 0.03)


def decide_stt_buffer_flush(
    *,
    buffer_len: int,
    flush_size: int,
    force: bool,
    socket_dead: bool,
    socket_available: bool,
    fair_use_dg_budget_exhausted: bool,
    fair_use_track_dg_usage: bool,
    sample_rate: int,
) -> SttBufferFlushDecision:
    if buffer_len == 0:
        return SttBufferFlushDecision(False, False, False, 0)
    if not force and buffer_len < flush_size:
        return SttBufferFlushDecision(False, False, False, 0)

    send_to_stt = socket_available and not socket_dead and not fair_use_dg_budget_exhausted
    dg_usage_ms = 0
    if send_to_stt and fair_use_track_dg_usage:
        dg_usage_ms = buffer_len * 1000 // (sample_rate * 2)
    return SttBufferFlushDecision(True, socket_dead, send_to_stt, dg_usage_ms)


def decide_multi_channel_stt_send(
    *, socket_available: bool, fair_use_dg_budget_exhausted: bool, pcm_len: int, fair_use_track_dg_usage: bool
) -> tuple[bool, int]:
    should_send = socket_available and not fair_use_dg_budget_exhausted
    dg_usage_ms = 0
    if should_send and fair_use_track_dg_usage:
        dg_usage_ms = pcm_len * 1000 // (TARGET_SAMPLE_RATE * 2)
    return should_send, dg_usage_ms


def decide_multi_channel_mix(buffers: Sequence[bytearray], audio_bytes_enabled: bool) -> MultiChannelMixDecision:
    if not audio_bytes_enabled:
        return MultiChannelMixDecision(False, 0)
    if not all(len(b) > 0 for b in buffers):
        return MultiChannelMixDecision(False, 0)
    min_len = min(len(b) for b in buffers)
    min_len = min_len - (min_len % 2)
    return MultiChannelMixDecision(min_len > 0, min_len)


def should_flush_final_multi_channel_mix(
    *, is_multi_channel: bool, audio_bytes_enabled: bool, buffers: Sequence[bytearray]
) -> bool:
    return is_multi_channel and audio_bytes_enabled and any(len(b) > 0 for b in buffers)


def should_skip_speaker_detection(
    *, person_id: Optional[str], is_user: bool, segment_id: str, suggested_segments: Sequence[str]
) -> bool:
    return bool(person_id) or is_user or segment_id in suggested_segments


def should_queue_speaker_embedding(
    *,
    speaker_id: Any,
    person_id: Optional[str],
    is_user: bool,
    speaker_id_enabled: bool,
    has_person_embeddings: bool,
    speaker_already_mapped: bool,
) -> bool:
    return (
        speaker_id_enabled
        and has_person_embeddings
        and speaker_id is not None
        and not person_id
        and not is_user
        and not speaker_already_mapped
    )


def should_spawn_speaker_match(*, speaker_already_mapped: bool, duration: float, min_audio_seconds: float) -> bool:
    return not speaker_already_mapped and duration >= min_audio_seconds


def decide_text_speaker_assignment(
    *,
    existing_person_id: Optional[str],
    create_speakers: bool,
    generated_person_id: str,
    speaker_auto_assign_enabled: bool,
) -> SpeakerTextAssignmentDecision:
    if existing_person_id:
        person_id = existing_person_id
        should_create_person = False
    elif create_speakers:
        person_id = generated_person_id
        should_create_person = True
    else:
        person_id = None
        should_create_person = False

    return SpeakerTextAssignmentDecision(
        person_id=person_id,
        should_create_person=should_create_person,
        event_person_id=person_id_for_client(person_id, speaker_auto_assign_enabled) if person_id else '',
        update_maps=person_id is not None,
    )


def is_user_self_match(person_id: Optional[str]) -> bool:
    return person_id == USER_SELF_PERSON_ID
