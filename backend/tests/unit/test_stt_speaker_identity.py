from utils.stt.speaker_identity import ConversationSpeakerIdAllocator, SpeakerProviderEpoch


def test_provider_change_scopes_padded_and_unpadded_speaker_numbers():
    epoch = SpeakerProviderEpoch('connection-a')
    allocator = ConversationSpeakerIdAllocator()
    deepgram = {'speaker': 'SPEAKER_0'}
    modulate = {'speaker': 'SPEAKER_00'}

    epoch.stamp([deepgram], 'deepgram')
    allocator.assign(deepgram)
    epoch.stamp([modulate], 'modulate')
    allocator.assign(modulate)

    assert deepgram['stt_provider'] == 'deepgram'
    assert modulate['stt_provider'] == 'modulate'
    assert deepgram['speaker_id_scope'] != modulate['speaker_id_scope']
    assert deepgram['speaker_id'] == 0
    assert modulate['speaker_id'] == 1


def test_reconnect_resumes_after_persisted_conversation_speaker_ids():
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(
        [
            {
                'speaker': 'SPEAKER_0',
                'speaker_id': 0,
                'speaker_id_scope': 'connection-a:0',
                'stt_provider': 'deepgram',
            }
        ]
    )
    reconnect_epoch = SpeakerProviderEpoch('connection-b')
    resumed = {'speaker': 'SPEAKER_0'}

    reconnect_epoch.stamp([resumed], 'deepgram')
    allocator.assign(resumed)

    assert resumed['speaker_id_scope'] == 'connection-b:0'
    assert resumed['speaker_id'] == 1


def test_segment_provider_survives_the_epoch_stamp():
    # The socket knows the peer that actually served the segment; the caller only
    # knows the host's configured selection. Overwriting the former with the latter
    # erased a real provider name in the hermetic e2e wire contract.
    epoch = SpeakerProviderEpoch('connection-a')
    served = {'speaker': 'SPEAKER_00', 'stt_provider': 'parakeet-wire-peer'}

    epoch.stamp([served], 'parakeet')

    assert served['stt_provider'] == 'parakeet-wire-peer'
    assert served['speaker_id_scope'] == 'connection-a:0'


def test_a_provider_change_inside_one_batch_opens_a_new_scope():
    epoch = SpeakerProviderEpoch('connection-a')
    first = {'speaker': 'SPEAKER_00', 'stt_provider': 'deepgram'}
    second = {'speaker': 'SPEAKER_00', 'stt_provider': 'modulate'}

    epoch.stamp([first, second], 'deepgram')

    # Same provider label, different provider: they must not share an identity space.
    assert first['speaker_id_scope'] != second['speaker_id_scope']

    allocator = ConversationSpeakerIdAllocator()
    allocator.assign(first)
    allocator.assign(second)
    assert first['speaker_id'] != second['speaker_id']


def test_segments_without_a_provider_fall_back_to_the_host_selection():
    epoch = SpeakerProviderEpoch('connection-a')
    unstamped = {'speaker': 'SPEAKER_00'}

    epoch.stamp([unstamped], 'parakeet')

    assert unstamped['stt_provider'] == 'parakeet'
    assert unstamped['speaker_id_scope'] == 'connection-a:0'
