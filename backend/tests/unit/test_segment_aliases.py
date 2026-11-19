"""Prompt-only segment aliases: the notes prompt numbers its turns, citations map back to stored ids."""

from types import SimpleNamespace

from utils.llm.segment_aliases import SegmentAliases, alias_transcript

A = '3f2b8c1e-9a4d-4e6f-b1c2-7d8e9f0a1b2c'
B = '0c9d8e7f-6a5b-4c3d-9e2f-1a0b9c8d7e6f'
C = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'
TRANSCRIPT = (
    'spk 1 ?\nspk 2 ?\n'
    f'[{A} 1] Launch moves to Thursday the 20th.\n\n'
    f'[{B}] The budget stays at eight thousand.\n\n'
    f'[{C} 2] Use S3 for the assets, see [{A}] above.'
)


def test_turn_headers_are_numbered_in_order_and_body_text_is_untouched():
    aliased, aliases = alias_transcript(TRANSCRIPT, [C, B, A])
    assert aliased.splitlines()[2] == '[seg1 1] Launch moves to Thursday the 20th.'
    assert '[seg2] The budget stays' in aliased
    assert '[seg3 2] Use S3 for the assets' in aliased
    assert f'see [{A}] above' in aliased, 'only line-opening headers are aliased, never quoted text'
    assert dict(aliases.to_id) == {'seg1': A, 'seg2': B, 'seg3': C}
    assert aliases.prompt_ids([C, B, A]) == ['seg1', 'seg2', 'seg3']


def test_citations_round_trip_to_stored_ids_and_unknown_refs_pass_through_for_validation():
    _, aliases = alias_transcript(TRANSCRIPT, [A, B, C])
    assert aliases.restore(['seg3', 'seg1', 'seg9', A, 'made-up']) == [C, A, 'seg9', A, 'made-up']
    structured = SimpleNamespace(
        sections=[SimpleNamespace(source_segment_ids=['seg1', 'seg2']), SimpleNamespace(source_segment_ids=[])],
        action_items=[SimpleNamespace(source_segment_ids=['seg3'])],
    )
    assert aliases.restore_structured(structured) is structured
    assert structured.sections[0].source_segment_ids == [A, B]
    assert structured.sections[1].source_segment_ids == []
    assert structured.action_items[0].source_segment_ids == [C]


def test_headers_of_unknown_ids_stay_as_they_are():
    aliased, aliases = alias_transcript(TRANSCRIPT, [A])
    assert aliased.count('[seg') == 1 and f'[{B}] The budget' in aliased and f'[{C} 2]' in aliased
    assert dict(aliases.to_id) == {'seg1': A}


def test_no_aliasing_when_a_stored_id_already_looks_like_an_alias():
    transcript = '[seg2 1] hello\n\n[x-1] world'
    aliased, aliases = alias_transcript(transcript, ['seg2', 'x-1'])
    assert aliased == transcript and not aliases.to_id
    assert aliases.prompt_ids(['seg2', 'x-1', '']) == ['seg2', 'x-1']
    structured = SimpleNamespace(sections=[SimpleNamespace(source_segment_ids=['seg2'])], action_items=[])
    assert aliases.restore_structured(structured).sections[0].source_segment_ids == ['seg2']


def test_empty_inputs_are_a_no_op():
    assert alias_transcript('', []) == ('', SegmentAliases())
    assert alias_transcript('plain text', [A]) == ('plain text', SegmentAliases())
    assert SegmentAliases().restore_structured(None) is None


def test_rendered_id_set_on_a_speaker_map_moves_to_alias_space_on_a_copy():
    class SpeakerMap(dict):
        pass

    speaker_map = SpeakerMap({'1': None})
    speaker_map.source_segment_ids = frozenset({A, B, 'not-rendered'})
    _, aliases = alias_transcript(TRANSCRIPT, [A, B, C])
    aliased = aliases.speaker_map(speaker_map)
    assert aliased.source_segment_ids == frozenset({'seg1', 'seg2'})
    assert speaker_map.source_segment_ids == frozenset({A, B, 'not-rendered'}), 'the original map is not changed'
    assert dict(aliased) == {'1': None}
    plain = {'1': None}
    assert aliases.speaker_map(plain) is plain


def test_each_header_shrinks_from_a_uuid_to_a_short_alias():
    aliased, _ = alias_transcript(TRANSCRIPT, [A, B, C])
    # Three headers, 36 characters each, become seg1..seg3 (4 characters each).
    assert len(TRANSCRIPT) - len(aliased) == 3 * (36 - 4)
