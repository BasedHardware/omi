"""Pre-recorded post-processing keeps the provider's casing after the first character.

Parakeet, Modulate and Deepgram return cased, punctuated text, and
``_merge_segments`` joins a speaker's sentences into one segment. Segment text
used ``str.capitalize()``, which also lowercased every later character: names,
acronyms, "I" and each later sentence start. Sync's text-based speaker naming
then never matched an introduction such as "my name is Sarah".
"""

from types import SimpleNamespace

from utils.stt.pre_recorded import postprocess_words
from utils.sync.speaker_identity import (
    PersonEmbeddingsCache,
    SpeakerIdentityDependencies,
    identify_speakers_for_segments,
)


def _entry(start, end, speaker, text):
    return {'timestamp': [start, end], 'speaker': speaker, 'text': text}


def test_merged_segment_keeps_provider_casing():
    segments = postprocess_words(
        [
            _entry(0.0, 1.4, 'SPEAKER_00', 'Yesterday I met Sarah at Google.'),
            _entry(1.5, 2.9, 'SPEAKER_00', 'NASA called back.'),
        ],
        0,
    )

    assert [segment.text for segment in segments] == ['Yesterday I met Sarah at Google. NASA called back.']


def test_first_character_is_still_capitalized():
    segments = postprocess_words([_entry(0.0, 1.0, 'SPEAKER_00', 'and then we left.')], 0)

    assert [segment.text for segment in segments] == ['And then we left.']


def test_sync_names_speaker_from_postprocessed_introduction():
    segments = postprocess_words([_entry(0.0, 2.0, 'SPEAKER_01', 'Hi, my name is Sarah.')], 0)
    people = {'Sarah': {'id': 'person-sarah', 'name': 'Sarah'}}
    dependencies = SpeakerIdentityDependencies(
        users_db=SimpleNamespace(get_person_by_name=lambda uid, name: people.get(name))
    )

    identify_speakers_for_segments(segments, None, PersonEmbeddingsCache(True), 'uid', dependencies=dependencies)

    assert segments[0].text == 'Hi, my name is Sarah.'
    assert segments[0].person_id == 'person-sarah'
    assert segments[0].speaker_match_source == 'sync_text'
