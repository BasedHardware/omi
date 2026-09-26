import numpy as np

from utils.stt.conversation_speakers import (
    Identity,
    resolve_conversation_speakers,
    significant_capture_speaker_ids,
)
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL

DIM = 64


def _voices(count, seed=7):
    rng = np.random.default_rng(seed)
    voices = rng.normal(size=(count, DIM))
    return voices / np.linalg.norm(voices, axis=1, keepdims=True)


def _clip(voice, rng, noise=0.35):
    """A clip embedding: the voice plus the noise short far-field clips carry."""
    vector = voice + rng.normal(scale=noise / np.sqrt(DIM), size=DIM)
    return vector / np.linalg.norm(vector)


def _fragmented(voice_plan, *, seconds=4.0, seed=11):
    """Segments where capture minted a new speaker_id for every segment (chunked sync)."""
    rng = np.random.default_rng(seed)
    voices = _voices(max(voice_plan) + 1)
    segments, embeddings = [], {}
    for index, voice in enumerate(voice_plan):
        segment = {
            'id': f's{index}',
            'speaker_id': index,
            'speaker': f'SPEAKER_{index}',
            'speaker_id_scope': f'sync:{index // 3}',
            'start': index * seconds,
            'end': index * seconds + seconds - 0.2,
            'is_user': False,
        }
        segments.append(segment)
        embeddings[segment['id']] = _clip(voices[voice], rng)
    return segments, embeddings, voices


def _voice_of(resolution, segments, plan):
    ids = {}
    for segment, voice in zip(segments, plan):
        ids.setdefault(voice, set()).add(resolution.speaker_ids[segment['id']])
    return ids


def test_fragmented_capture_ids_resolve_to_one_id_per_voice():
    plan = [0, 1, 0, 2, 0, 1] * 8
    segments, embeddings, _ = _fragmented(plan)

    resolution = resolve_conversation_speakers(segments, embeddings)

    by_voice = _voice_of(resolution, segments, plan)
    assert all(len(ids) == 1 for ids in by_voice.values())
    assert len({next(iter(ids)) for ids in by_voice.values()}) == 3
    assert resolution.input_speaker_ids == len(plan)
    assert sorted(resolution.significant_speaker_ids) == sorted(next(iter(ids)) for ids in by_voice.values())


def test_resolution_is_stable_when_rerun_on_its_own_output():
    plan = [0, 1, 2, 1, 0, 2] * 6
    segments, embeddings, _ = _fragmented(plan)
    first = resolve_conversation_speakers(segments, embeddings)
    for segment in segments:
        segment['speaker_id'] = first.speaker_ids[segment['id']]

    second = resolve_conversation_speakers(segments, embeddings)

    assert second.speaker_ids == first.speaker_ids


def test_a_voice_that_barely_spoke_is_not_a_participant():
    plan = [0, 1] * 10 + [2]
    segments, embeddings, _ = _fragmented(plan, seconds=3.0)

    resolution = resolve_conversation_speakers(segments, embeddings)

    brief = resolution.speaker_ids[segments[-1]['id']]
    assert brief not in resolution.significant_speaker_ids
    assert len(resolution.significant_speaker_ids) == 2


def test_manually_labeled_speaker_keeps_its_id_and_labels_the_whole_voice():
    plan = [0, 1] * 10
    segments, embeddings, _ = _fragmented(plan)
    labeled = segments[2]['speaker_id']  # a voice-0 fragment the user named

    resolution = resolve_conversation_speakers(
        segments, embeddings, manual_speakers={labeled: Identity(is_user=False, person_id='nick')}
    )

    voice_zero = {resolution.speaker_ids[s['id']] for s, v in zip(segments, plan) if v == 0}
    assert voice_zero == {labeled}


def test_two_labeled_identities_are_never_merged_even_when_voices_match():
    plan = [0] * 12
    segments, embeddings, _ = _fragmented(plan)

    resolution = resolve_conversation_speakers(
        segments,
        embeddings,
        manual_speakers={
            segments[0]['speaker_id']: Identity(is_user=False, person_id='nick'),
            segments[5]['speaker_id']: Identity(is_user=False, person_id='tin'),
        },
    )

    assert resolution.speaker_ids['s0'] == segments[0]['speaker_id']
    assert resolution.speaker_ids['s5'] == segments[5]['speaker_id']


def test_fragments_labeled_with_one_person_merge_into_one_voice():
    plan = [0, 1] * 6
    segments, embeddings, _ = _fragmented(plan)
    nick = Identity(is_user=False, person_id='nick')

    resolution = resolve_conversation_speakers(
        segments,
        embeddings,
        manual_speakers={segments[1]['speaker_id']: nick, segments[7]['speaker_id']: nick},
    )

    assert resolution.speaker_ids['s1'] == resolution.speaker_ids['s7']


def test_owner_voiceprint_names_the_voice_and_joins_its_split_clusters():
    # Two recording conditions (voices 0 and 1, orthogonal) split the owner into
    # two clusters too far apart to cluster or absorb; the voiceprint sits
    # between them and matches both. Voice 2 is someone else.
    plan = [0, 1, 2] * 10
    segments, embeddings, voices = _fragmented(plan)
    owner_print = voices[0] + voices[1]

    without_print = resolve_conversation_speakers(segments, embeddings)
    split = {without_print.speaker_ids[s['id']] for s, v in zip(segments, plan) if v in (0, 1)}
    assert len(split) == 2

    resolution = resolve_conversation_speakers(segments, embeddings, voiceprints={'user': owner_print})

    owner_ids = {resolution.speaker_ids[s['id']] for s, v in zip(segments, plan) if v in (0, 1)}
    assert len(owner_ids) == 1
    identity = resolution.voice_identities[next(iter(owner_ids))]
    assert identity.is_user and identity.person_id is None
    other = resolution.speaker_ids['s2']
    assert other not in owner_ids and other not in resolution.voice_identities


def test_voiceprint_never_overrides_a_manual_label():
    plan = [0, 1] * 8
    segments, embeddings, voices = _fragmented(plan)

    resolution = resolve_conversation_speakers(
        segments,
        embeddings,
        manual_speakers={segments[0]['speaker_id']: Identity(is_user=False, person_id='nick')},
        voiceprints={'user': voices[0]},
    )

    assert resolution.speaker_ids['s0'] not in resolution.voice_identities


def test_short_segments_inherit_capture_label_then_nearest_voice():
    plan = [0, 1] * 6
    segments, embeddings, _ = _fragmented(plan)
    segments.append({'id': 'short-a', 'speaker_id': 2, 'start': 8.1, 'end': 8.5, 'is_user': False})
    segments.append({'id': 'short-b', 'speaker_id': 500, 'start': 41.0, 'end': 41.3, 'is_user': False})

    resolution = resolve_conversation_speakers(segments, embeddings)

    assert resolution.speaker_ids['short-a'] == resolution.speaker_ids['s2']
    assert resolution.speaker_ids['short-b'] == resolution.speaker_ids['s10']


def test_onboarding_sentinel_segments_are_left_alone():
    plan = [0, 1] * 4
    segments, embeddings, _ = _fragmented(plan)
    segments.append({'id': 'omi', 'speaker_id': OMI_SPEAKER_ID_SENTINEL, 'start': 1, 'end': 3, 'is_user': False})
    embeddings['omi'] = embeddings['s0']

    resolution = resolve_conversation_speakers(segments, embeddings)

    assert 'omi' not in resolution.speaker_ids
    assert OMI_SPEAKER_ID_SENTINEL not in resolution.speaker_ids.values()


def test_new_ids_never_reuse_a_receipt_key_whose_segments_are_gone():
    plan = [0, 1, 2]
    segments, embeddings, _ = _fragmented(plan)
    for segment in segments:
        segment['speaker_id'] = 0  # everything collided on one capture id
    orphan = 3

    resolution = resolve_conversation_speakers(
        segments, embeddings, manual_speakers={orphan: Identity(is_user=False, person_id='gone')}
    )

    assert orphan not in resolution.speaker_ids.values()
    assert len(set(resolution.speaker_ids.values())) == 3


def test_nothing_to_resolve_without_embeddings():
    segments, _, _ = _fragmented([0, 1])
    assert resolve_conversation_speakers(segments, {}) is None


def test_capture_participants_are_the_voices_that_spoke_long_enough():
    segments = [
        {'speaker_id': 0, 'start': 0, 'end': 30},
        {'speaker_id': 1, 'start': 30, 'end': 33},
        {'speaker_id': OMI_SPEAKER_ID_SENTINEL, 'start': 33, 'end': 60},
    ]
    assert significant_capture_speaker_ids(segments) == [0]


def test_a_voice_near_but_not_at_the_owner_print_stays_someone_else():
    # Measured on a pendant goodbye: the owner's pooled voice sat 0.30 from the
    # voiceprint, while a far-field companion pooled at 0.63 — inside the per-clip
    # enrollment threshold, so it was named the owner and merged into them.
    plan = [0, 1] * 10
    segments, embeddings, voices = _fragmented(plan, seed=5)
    orthogonal = voices[1] - (voices[1] @ voices[0]) * voices[0]
    companion = 0.4 * voices[0] + np.sqrt(1 - 0.16) * orthogonal / np.linalg.norm(orthogonal)
    # Far-field clips are noisy: pairwise they sit past the clustering cut even
    # though the pooled companion voice is only 0.6 from the owner's voiceprint.
    rng = np.random.default_rng(8)
    for segment, voice in zip(segments, plan):
        embeddings[segment['id']] = _clip(companion if voice else voices[0], rng, noise=1.0)

    resolution = resolve_conversation_speakers(segments, embeddings, voiceprints={'user': voices[0]})

    owner = resolution.speaker_ids['s0']
    companion_id = resolution.speaker_ids['s1']
    assert companion_id != owner
    assert resolution.voice_identities[owner].is_user
    assert companion_id not in resolution.voice_identities


def test_segments_not_yet_embedded_keep_capture_ids_and_lower_coverage():
    plan = [0, 1] * 10
    segments, embeddings, _ = _fragmented(plan)
    for index in range(10, 20):  # the second half ran out of budget
        del embeddings[f's{index}']

    resolution = resolve_conversation_speakers(segments, embeddings)

    assert all(f's{index}' not in resolution.speaker_ids for index in range(10, 20))
    assert abs(resolution.coverage - 0.5) < 1e-9
