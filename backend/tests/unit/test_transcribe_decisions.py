from utils.transcribe_decisions import (
    ConversationLifecycleAction,
    TARGET_SAMPLE_RATE,
    USER_SELF_PERSON_ID,
    decide_existing_conversation_action,
    decide_lifecycle_action,
    decide_multi_channel_mix,
    decide_multi_channel_stt_send,
    decide_stt_buffer_flush,
    decide_text_speaker_assignment,
    effective_conversation_timeout,
    is_user_self_match,
    normalize_codec_frame,
    normalize_language,
    person_id_for_client,
    select_translation_language,
    should_enable_speaker_identification,
    should_flush_final_multi_channel_mix,
    should_force_single_language,
    should_include_speech_profile,
    should_initialize_vad_gate,
    should_load_speech_profile,
    should_process_on_disconnect,
    should_queue_speaker_embedding,
    should_remove_in_progress_pointer,
    should_skip_speaker_detection,
    should_spawn_speaker_match,
    stt_buffer_flush_size,
    vad_gate_mode,
)


def test_startup_decisions_pin_current_overrides():
    assert should_include_speech_profile(True, is_multi_channel=False, onboarding_mode=False) is True
    assert should_include_speech_profile(True, is_multi_channel=True, onboarding_mode=False) is False
    assert should_include_speech_profile(True, is_multi_channel=False, onboarding_mode=True) is False

    assert should_force_single_language(onboarding_mode=True, single_language_mode=False) is True
    assert should_force_single_language(onboarding_mode=False, single_language_mode=False) is False

    assert normalize_language('auto') == 'multi'
    assert normalize_language('en') == 'en'


def test_codec_frame_normalization_pins_special_codecs():
    opus = normalize_codec_frame('opus_fs320')
    assert opus.codec == 'opus'
    assert opus.frame_size == 320
    assert opus.lc3_chunk_size is None
    assert opus.lc3_frame_duration_us is None

    lc3 = normalize_codec_frame('lc3_fs1030')
    assert lc3.codec == 'lc3'
    assert lc3.frame_size == 160
    assert lc3.lc3_chunk_size == 30
    assert lc3.lc3_frame_duration_us == 10000

    pcm = normalize_codec_frame('pcm8')
    assert pcm.codec == 'pcm8'
    assert pcm.frame_size == 160


def test_translation_language_gating():
    assert (
        select_translation_language(
            single_language_mode=True,
            stt_language='multi',
            language='es',
            user_language_preference='fr',
        )
        is None
    )
    assert (
        select_translation_language(
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='fr',
        )
        == 'fr'
    )
    assert (
        select_translation_language(
            single_language_mode=False,
            stt_language='multi',
            language='multi',
            user_language_preference='',
        )
        is None
    )
    assert (
        select_translation_language(
            single_language_mode=False,
            stt_language='multi',
            language='es',
            user_language_preference='fr',
        )
        == 'es'
    )
    assert (
        select_translation_language(
            single_language_mode=False,
            stt_language='en',
            language='en',
            user_language_preference='fr',
        )
        is None
    )


def test_translation_language_rejects_sentinel_preferences():
    # Legacy Firestore users/{uid}.language rows hold the STT sentinel itself; sending it
    # to NLLB as a target is always an unsupported_target 400 + a Google fallback (#9623).
    for sentinel in ('multi', 'auto'):
        assert (
            select_translation_language(
                single_language_mode=False,
                stt_language='multi',
                language='multi',
                user_language_preference=sentinel,
            )
            is None
        )

    # An un-normalized 'auto' request language is a sentinel too, never a target.
    assert (
        select_translation_language(
            single_language_mode=False,
            stt_language='multi',
            language='auto',
            user_language_preference='fr',
        )
        is None
    )


def test_effective_conversation_timeout_pins_current_quirks():
    assert effective_conversation_timeout(30, is_multi_channel=False) == 120
    assert effective_conversation_timeout(120, is_multi_channel=False) == 120
    assert effective_conversation_timeout(-1, is_multi_channel=False) == 4 * 60 * 60
    assert effective_conversation_timeout(999999, is_multi_channel=False) == 999999
    assert effective_conversation_timeout(999999, is_multi_channel=True) == 4 * 60 * 60


def test_speech_profile_and_speaker_id_gates():
    assert should_load_speech_profile(use_custom_stt=False, is_multi_channel=False, include_speech_profile=True) is True
    assert should_load_speech_profile(use_custom_stt=True, is_multi_channel=False, include_speech_profile=True) is False
    assert should_load_speech_profile(use_custom_stt=False, is_multi_channel=True, include_speech_profile=True) is False

    assert (
        should_enable_speaker_identification(
            use_custom_stt=False,
            private_cloud_sync_enabled=False,
            has_speech_profile=True,
        )
        is True
    )
    assert (
        should_enable_speaker_identification(
            use_custom_stt=False,
            private_cloud_sync_enabled=True,
            has_speech_profile=False,
        )
        is True
    )
    assert (
        should_enable_speaker_identification(
            use_custom_stt=True,
            private_cloud_sync_enabled=True,
            has_speech_profile=True,
        )
        is False
    )


def test_conversation_lifecycle_actions():
    assert (
        decide_existing_conversation_action(seconds_since_last_segment=119.9, conversation_creation_timeout=120)
        == ConversationLifecycleAction.continue_current
    )
    assert (
        decide_existing_conversation_action(seconds_since_last_segment=120, conversation_creation_timeout=120)
        == ConversationLifecycleAction.process_and_create_new
    )

    assert (
        decide_lifecycle_action(
            conversation_exists=False,
            status=None,
            in_progress_status='in_progress',
            seconds_since_last_update=None,
            conversation_creation_timeout=120,
        )
        == ConversationLifecycleAction.create_new
    )
    assert (
        decide_lifecycle_action(
            conversation_exists=True,
            status='processing',
            in_progress_status='in_progress',
            seconds_since_last_update=None,
            conversation_creation_timeout=120,
        )
        == ConversationLifecycleAction.create_new
    )
    assert (
        decide_lifecycle_action(
            conversation_exists=True,
            status='in_progress',
            in_progress_status='in_progress',
            seconds_since_last_update=120,
            conversation_creation_timeout=120,
        )
        == ConversationLifecycleAction.process_and_create_new
    )


def test_disconnect_processing_only_targets_single_channel_in_progress_with_content():
    content_conversation = {
        'status': 'in_progress',
        'source': 'desktop',
        'transcript_segments': [{'text': 'synthetic transcript'}],
        'photos': [],
    }

    assert (
        should_process_on_disconnect(
            is_multi_channel=False,
            close_code=1000,
            conversation_id='conversation-1',
            conversation=content_conversation,
            in_progress_status='in_progress',
        )
        is True
    )

    assert (
        should_process_on_disconnect(
            is_multi_channel=True,
            close_code=1000,
            conversation_id='conversation-1',
            conversation=content_conversation,
            in_progress_status='in_progress',
        )
        is False
    )

    assert (
        should_process_on_disconnect(
            is_multi_channel=False,
            close_code=1001,
            conversation_id='conversation-1',
            conversation=content_conversation,
            in_progress_status='in_progress',
        )
        is False
    )

    assert (
        should_process_on_disconnect(
            is_multi_channel=False,
            close_code=1000,
            conversation_id='conversation-1',
            conversation={**content_conversation, 'status': 'processing'},
            in_progress_status='in_progress',
        )
        is False
    )

    assert (
        should_process_on_disconnect(
            is_multi_channel=False,
            close_code=1000,
            conversation_id='conversation-1',
            conversation={'status': 'in_progress', 'transcript_segments': [], 'photos': []},
            in_progress_status='in_progress',
        )
        is False
    )


def test_disconnect_processing_rejects_non_desktop_clean_close_with_content():
    phone_conversation = {
        'status': 'in_progress',
        'source': 'phone',
        'transcript_segments': [{'text': 'synthetic transcript'}],
        'photos': [],
    }

    assert (
        should_process_on_disconnect(
            is_multi_channel=False,
            close_code=1000,
            conversation_id='conversation-1',
            conversation=phone_conversation,
            in_progress_status='in_progress',
        )
        is False
    )


def test_disconnect_processing_accepts_enum_like_desktop_source():
    class Source:
        value = 'desktop'

    desktop_conversation = {
        'status': 'in_progress',
        'source': Source(),
        'transcript_segments': [{'text': 'synthetic transcript'}],
        'photos': [],
    }

    assert (
        should_process_on_disconnect(
            is_multi_channel=False,
            close_code=1000,
            conversation_id='conversation-1',
            conversation=desktop_conversation,
            in_progress_status='in_progress',
        )
        is True
    )


def test_in_progress_pointer_removal_requires_matching_conversation_id():
    assert (
        should_remove_in_progress_pointer(current_in_progress_id='conversation-1', conversation_id='conversation-1')
        is True
    )
    assert (
        should_remove_in_progress_pointer(current_in_progress_id='newer-conversation', conversation_id='conversation-1')
        is False
    )
    assert should_remove_in_progress_pointer(current_in_progress_id='conversation-1', conversation_id=None) is False
    assert should_remove_in_progress_pointer(current_in_progress_id='', conversation_id='conversation-1') is False


def test_vad_gate_override_decisions():
    assert should_initialize_vad_gate(override='disabled', global_gate_enabled=True) is False
    assert should_initialize_vad_gate(override='enabled', global_gate_enabled=False) is True
    assert should_initialize_vad_gate(override=None, global_gate_enabled=True) is True
    assert should_initialize_vad_gate(override=None, global_gate_enabled=False) is False
    assert vad_gate_mode(override='enabled', default_mode='passive') == 'active'
    assert vad_gate_mode(override=None, default_mode='passive') == 'passive'


def test_stt_buffer_flush_waits_for_budget_and_force_flushes():
    flush_size = stt_buffer_flush_size(16000)
    assert flush_size == 960

    small = decide_stt_buffer_flush(
        buffer_len=flush_size - 1,
        flush_size=flush_size,
        force=False,
        socket_dead=False,
        socket_available=True,
        fair_use_dg_budget_exhausted=False,
        fair_use_track_dg_usage=True,
        sample_rate=16000,
    )
    assert small.should_flush is False

    forced = decide_stt_buffer_flush(
        buffer_len=100,
        flush_size=flush_size,
        force=True,
        socket_dead=False,
        socket_available=True,
        fair_use_dg_budget_exhausted=False,
        fair_use_track_dg_usage=True,
        sample_rate=16000,
    )
    assert forced.should_flush is True
    assert forced.send_to_stt is True
    assert forced.dg_usage_ms == 100 * 1000 // (16000 * 2)


def test_stt_buffer_flush_empty_buffer_is_noop():
    empty = decide_stt_buffer_flush(
        buffer_len=0,
        flush_size=960,
        force=False,
        socket_dead=False,
        socket_available=True,
        fair_use_dg_budget_exhausted=False,
        fair_use_track_dg_usage=True,
        sample_rate=16000,
    )
    assert empty.should_flush is False


def test_stt_buffer_flush_dead_socket_and_budget_do_not_send_or_bill():
    dead = decide_stt_buffer_flush(
        buffer_len=960,
        flush_size=960,
        force=False,
        socket_dead=True,
        socket_available=True,
        fair_use_dg_budget_exhausted=False,
        fair_use_track_dg_usage=True,
        sample_rate=16000,
    )
    assert dead.should_flush is True
    assert dead.socket_dead is True
    assert dead.send_to_stt is False
    assert dead.dg_usage_ms == 0

    exhausted = decide_stt_buffer_flush(
        buffer_len=960,
        flush_size=960,
        force=False,
        socket_dead=False,
        socket_available=True,
        fair_use_dg_budget_exhausted=True,
        fair_use_track_dg_usage=True,
        sample_rate=16000,
    )
    assert exhausted.should_flush is True
    assert exhausted.send_to_stt is False
    assert exhausted.dg_usage_ms == 0


def test_multi_channel_send_and_mix_plans():
    should_send, dg_ms = decide_multi_channel_stt_send(
        socket_available=True,
        fair_use_dg_budget_exhausted=False,
        pcm_len=TARGET_SAMPLE_RATE * 2,
        fair_use_track_dg_usage=True,
    )
    assert should_send is True
    assert dg_ms == 1000

    blocked, blocked_ms = decide_multi_channel_stt_send(
        socket_available=True,
        fair_use_dg_budget_exhausted=True,
        pcm_len=TARGET_SAMPLE_RATE * 2,
        fair_use_track_dg_usage=True,
    )
    assert blocked is False
    assert blocked_ms == 0

    not_ready = decide_multi_channel_mix([bytearray(b'ab'), bytearray()], audio_bytes_enabled=True)
    assert not_ready.should_mix is False
    assert not_ready.min_len == 0

    ready = decide_multi_channel_mix([bytearray(b'abcde'), bytearray(b'abcd')], audio_bytes_enabled=True)
    assert ready.should_mix is True
    assert ready.min_len == 4

    disabled = decide_multi_channel_mix([bytearray(b'ab'), bytearray(b'ab')], audio_bytes_enabled=False)
    assert disabled.should_mix is False


def test_final_multi_channel_flush_decision():
    assert (
        should_flush_final_multi_channel_mix(
            is_multi_channel=True,
            audio_bytes_enabled=True,
            buffers=[bytearray(), bytearray(b'ab')],
        )
        is True
    )
    assert (
        should_flush_final_multi_channel_mix(
            is_multi_channel=False,
            audio_bytes_enabled=True,
            buffers=[bytearray(b'ab')],
        )
        is False
    )
    assert (
        should_flush_final_multi_channel_mix(
            is_multi_channel=True,
            audio_bytes_enabled=False,
            buffers=[bytearray(b'ab')],
        )
        is False
    )


def test_client_person_id_gate_and_user_sentinel():
    assert person_id_for_client('p1', speaker_auto_assign_enabled=True) == 'p1'
    assert person_id_for_client('p1', speaker_auto_assign_enabled=False) == ''
    assert person_id_for_client(None, speaker_auto_assign_enabled=True) == ''
    assert USER_SELF_PERSON_ID == 'user'
    assert is_user_self_match('user') is True
    assert is_user_self_match('p1') is False


def test_speaker_detection_gates():
    assert (
        should_skip_speaker_detection(person_id='p1', is_user=False, segment_id='s1', suggested_segments=set()) is True
    )
    assert should_skip_speaker_detection(person_id='', is_user=True, segment_id='s1', suggested_segments=set()) is True
    assert (
        should_skip_speaker_detection(person_id='', is_user=False, segment_id='s1', suggested_segments={'s1'}) is True
    )
    assert (
        should_skip_speaker_detection(person_id='', is_user=False, segment_id='s1', suggested_segments=set()) is False
    )

    assert (
        should_queue_speaker_embedding(
            speaker_id=1,
            person_id='',
            is_user=False,
            speaker_id_enabled=True,
            has_person_embeddings=True,
            speaker_already_mapped=False,
        )
        is True
    )
    assert (
        should_queue_speaker_embedding(
            speaker_id=None,
            person_id='',
            is_user=False,
            speaker_id_enabled=True,
            has_person_embeddings=True,
            speaker_already_mapped=False,
        )
        is False
    )
    assert should_spawn_speaker_match(speaker_already_mapped=False, duration=2.0, min_audio_seconds=2.0) is True
    assert should_spawn_speaker_match(speaker_already_mapped=False, duration=1.99, min_audio_seconds=2.0) is False
    assert should_spawn_speaker_match(speaker_already_mapped=True, duration=4.0, min_audio_seconds=2.0) is False


def test_text_speaker_assignment_create_speakers_compatibility():
    existing = decide_text_speaker_assignment(
        existing_person_id='p1',
        create_speakers=False,
        generated_person_id='new',
        speaker_auto_assign_enabled=True,
    )
    assert existing.person_id == 'p1'
    assert existing.should_create_person is False
    assert existing.event_person_id == 'p1'
    assert existing.update_maps is True

    created_old_client = decide_text_speaker_assignment(
        existing_person_id=None,
        create_speakers=True,
        generated_person_id='new',
        speaker_auto_assign_enabled=False,
    )
    assert created_old_client.person_id == 'new'
    assert created_old_client.should_create_person is True
    assert created_old_client.event_person_id == ''
    assert created_old_client.update_maps is True

    no_create = decide_text_speaker_assignment(
        existing_person_id=None,
        create_speakers=False,
        generated_person_id='new',
        speaker_auto_assign_enabled=True,
    )
    assert no_create.person_id is None
    assert no_create.should_create_person is False
    assert no_create.event_person_id == ''
    assert no_create.update_maps is False
