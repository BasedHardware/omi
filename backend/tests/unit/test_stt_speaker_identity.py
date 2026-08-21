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
