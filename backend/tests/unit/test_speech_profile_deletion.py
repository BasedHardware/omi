from utils.speech_profile_deletion import teaching_segment_ids_for_deleted_sample


def test_deleted_sample_clears_the_teaching_segments_from_that_conversation():
    person = {'speech_sample_source': {'conversation_id': 'conv-1', 'segment_ids': ['s1', 's2']}}

    assert teaching_segment_ids_for_deleted_sample(person, 'conv-1') == ['s1', 's2']


def test_deleted_sample_from_another_conversation_keeps_the_profile():
    person = {'speech_sample_source': {'conversation_id': 'conv-1', 'segment_ids': ['s1']}}

    assert teaching_segment_ids_for_deleted_sample(person, 'conv-2') == []


def test_missing_person_or_source_does_not_clear_a_profile():
    assert teaching_segment_ids_for_deleted_sample(None, 'conv-1') == []
    assert teaching_segment_ids_for_deleted_sample({}, 'conv-1') == []
    assert teaching_segment_ids_for_deleted_sample({'speech_sample_source': {}}, '') == []
