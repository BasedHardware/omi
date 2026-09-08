from utils.stt.speaker_identity import (
    OMI_SPEAKER_ID_SENTINEL,
    ConversationSpeakerIdAllocator,
    SpeakerProviderEpoch,
)


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


def test_provider_fallback_mid_conversation_keeps_peer_identities_separate():
    # A live conversation can fall back between serving peers mid-stream, and
    # each peer restarts its own SPEAKER_00 numbering. If the two numbering
    # spaces were shared, the first speaker after the transition would inherit
    # the other peer's identity (and its person assignment).
    epoch = SpeakerProviderEpoch('connection-a')
    allocator = ConversationSpeakerIdAllocator()

    peer_one_alice = {'speaker': 'SPEAKER_00', 'stt_provider': 'deepgram'}
    peer_one_bob = {'speaker': 'SPEAKER_01', 'stt_provider': 'deepgram'}
    epoch.stamp([peer_one_alice, peer_one_bob], 'deepgram')
    allocator.assign(peer_one_alice)
    allocator.assign(peer_one_bob)

    peer_two_first = {'speaker': 'SPEAKER_00', 'stt_provider': 'modulate'}
    peer_two_second = {'speaker': 'SPEAKER_01', 'stt_provider': 'modulate'}
    epoch.stamp([peer_two_first, peer_two_second], 'deepgram')
    allocator.assign(peer_two_first)
    allocator.assign(peer_two_second)

    # Same provider-local label, different peer: must never share an ID.
    assert peer_one_alice['speaker_id'] != peer_two_first['speaker_id']
    assert peer_one_bob['speaker_id'] != peer_two_second['speaker_id']
    # Within one peer the labels stay stable and distinct.
    assert peer_one_alice['speaker_id'] != peer_one_bob['speaker_id']
    assert peer_two_first['speaker_id'] != peer_two_second['speaker_id']
    # The epoch only moves forward: a peer whose name returns after an
    # interlude gets a NEW scope rather than rejoining its old numbering space.
    # Rejoining would be wrong whenever the peer actually restarted (its
    # SPEAKER_00 may be a different human), and merging numbering spaces is the
    # one mistake this design refuses to make — the cost is at most a split
    # identity, never a stolen one.
    peer_one_alice_again = {'speaker': 'SPEAKER_00', 'stt_provider': 'deepgram'}
    epoch.stamp([peer_one_alice_again], 'deepgram')
    allocator.assign(peer_one_alice_again)
    assert peer_one_alice_again['speaker_id'] not in {
        peer_one_alice['speaker_id'],
        peer_two_first['speaker_id'],
    }
    assert peer_one_alice_again['speaker_id_scope'] != peer_one_alice['speaker_id_scope']


def test_reconnect_rehydrates_without_reuse_or_renumbering():
    # A websocket reconnect builds a fresh epoch (new connection scope) but the
    # conversation keeps its persisted segments. Rehydration must guarantee two
    # things: no previously issued ID is handed to a new speaker, and no
    # persisted assignment is recomputed to a different value.
    allocator = ConversationSpeakerIdAllocator()
    persisted = [
        {'speaker': 'SPEAKER_00', 'speaker_id': 0, 'speaker_id_scope': 'connection-a:0'},
        {'speaker': 'SPEAKER_01', 'speaker_id': 1, 'speaker_id_scope': 'connection-a:0'},
    ]
    allocator.hydrate(persisted)

    reconnect_epoch = SpeakerProviderEpoch('connection-b')
    resumed_speaker = {'speaker': 'SPEAKER_00'}
    reconnect_epoch.stamp([resumed_speaker], 'deepgram')
    allocator.assign(resumed_speaker)
    assert resumed_speaker['speaker_id'] == 2  # not 0 and not 1: no reuse

    # The old numbering space keeps resolving to its persisted IDs, so nothing
    # already shown to the user gets renumbered after the reconnect.
    replayed = {'speaker': 'SPEAKER_01', 'speaker_id_scope': 'connection-a:0'}
    allocator.assign(replayed)
    assert replayed['speaker_id'] == 1


def test_allocator_never_allocates_the_onboarding_sentinel():
    # Omi's onboarding questions ride the same transcript pipeline with
    # speaker_id=99 (OnboardingHandler.OMI_SPEAKER_ID), and transcripts.py
    # distinguishes them by exact value. Provider transitions multiply scopes,
    # so a long flapping session can push the allocation counter past 98 — the
    # allocator must skip 99 rather than hand a real speaker the sentinel.
    # (The sentinel's equality with OnboardingHandler.OMI_SPEAKER_ID is pinned
    # in test_listen_runtime_regressions.py, which already owns that import.)
    allocator = ConversationSpeakerIdAllocator()
    assigned = []
    for index in range(120):
        segment = {'speaker_id_scope': f'connection-a:{index}', 'speaker': 'SPEAKER_00'}
        allocator.assign(segment)
        assigned.append(segment['speaker_id'])

    assert OMI_SPEAKER_ID_SENTINEL not in assigned
    # The skip is a single hole: every other ID is allocated in order.
    assert assigned == [value for value in range(121) if value != OMI_SPEAKER_ID_SENTINEL]


def test_padded_and_unpadded_labels_share_one_identity():
    # Providers disagree on zero padding (Deepgram/Modulate emit SPEAKER_02,
    # Parakeet paths emit SPEAKER_2), and a custom-STT client may send a bare
    # speaker_id with no label at all. If the allocator keyed on the raw
    # spelling, one human inside one provider scope could split into two
    # speakers depending on which segment arrived first.
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate([{'speaker': 'SPEAKER_02', 'speaker_id': 2, 'speaker_id_scope': 'connection-a:0'}])

    unpadded = {'speaker': 'SPEAKER_2', 'speaker_id_scope': 'connection-a:0'}
    unlabeled = {'speaker_id': 2, 'speaker_id_scope': 'connection-a:0'}
    allocator.assign(unpadded)
    allocator.assign(unlabeled)

    assert unpadded['speaker_id'] == 2
    assert unlabeled['speaker_id'] == 2

    # Distinct speakers still stay distinct: SPEAKER_10 is not SPEAKER_1.
    ten = {'speaker': 'SPEAKER_10', 'speaker_id_scope': 'connection-a:0'}
    allocator.assign(ten)
    assert ten['speaker_id'] not in {2}


def test_legacy_segments_without_a_scope_pass_through_unharmed():
    # Conversations recorded before scoping exists (and Omi's onboarding
    # segments today) carry no speaker_id_scope. They must leave the allocator
    # untouched: no new key registered, no speaker_id rewritten, so legacy
    # provider-local numbering and the 99 sentinel survive verbatim.
    allocator = ConversationSpeakerIdAllocator()
    legacy = {'speaker': 'SPEAKER_07', 'speaker_id': 7}
    sentinel = {'speaker': 'SPEAKER_99', 'speaker_id': 99}

    allocator.assign(legacy)
    allocator.assign(sentinel)

    assert legacy['speaker_id'] == 7
    assert sentinel['speaker_id'] == 99
    assert allocator._speaker_ids == {}
