"""Bulk media exclusion uses the persisted manual decision, without voice learning.

Load the route's functions without initializing unrelated provider clients. The
assignment policy and teaching scheduler remain the production implementations.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import ANY, Mock, call

from fastapi import BackgroundTasks, Depends, HTTPException
from models.conversation import BulkAssignSegmentsRequest
from models.transcript_segment import TranscriptSegment
from utils.manual_speaker_assignments import manual_assignment, apply_manual_assignments, manual_rejected_speakers
from utils.ignored_voice_markers import record_exclusion_markers, retire_exclusion_markers
from utils.speaker_tag_prompts.selection import _manually_decided
from utils.person_evidence import assignment_evidence, receipt_person_ids

BACKEND = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace):
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)


def test_bulk_not_a_person_is_resolved_persisted_reversible_and_never_teaches():
    raw = {
        'id': 'conversation',
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 4, 'is_user': True, 'person_id': None, 'start': 0, 'end': 2, 'text': 'TV'},
            {'id': 's2', 'speaker_id': 4, 'is_user': False, 'person_id': 'p1', 'start': 2, 'end': 4, 'text': 'movie'},
            {'id': 's3', 'speaker_id': 7, 'is_user': False, 'person_id': None, 'start': 4, 'end': 6, 'text': 'human'},
        ],
    }
    learning = Mock()
    ignored = Mock()
    cleared = Mock()
    namespace = dict(
        Optional=Optional,
        List=list,
        Sequence=list,
        Mapping=dict,
        Any=object,
        datetime=__import__('datetime').datetime,
        timezone=__import__('datetime').timezone,
        voice_profiles_db=SimpleNamespace(record_ignored_voice=ignored, clear_ignored_voices=cleared),
        record_exclusion_markers=lambda uid, cid, raw, resolved, **kwargs: record_exclusion_markers(
            uid, cid, raw, resolved, voice_profiles=SimpleNamespace(record_ignored_voice=ignored), **kwargs
        ),
        retire_exclusion_markers=lambda uid, cid, raw, resolved, **kwargs: retire_exclusion_markers(
            uid, cid, raw, resolved, voice_profiles=SimpleNamespace(clear_ignored_voices=cleared), **kwargs
        ),
        manual_rejected_speakers=manual_rejected_speakers,
        teaching_segment_ids=lambda segments, resolved: resolved,
        delete_speech_profile_blob=Mock(),
        run_authorized_person_learning=learning,
        run_authorized_owner_learning=learning,
    )

    def assign(uid, conversation_id, **kwargs):
        before = list(raw['transcript_segments'])
        segments, receipt, resolved, previous = manual_assignment(raw, **kwargs)
        raw.update(transcript_segments=segments, manual_speaker_assignments=receipt)
        return raw, resolved, [], before

    namespace['conversations_db'] = SimpleNamespace(assign_conversation_speaker=assign)
    load_functions(
        BACKEND / 'utils/speaker_assignment_teaching.py',
        {'commit_manual_assignment', 'schedule_assignment_teaching'},
        namespace,
    )
    namespace.update(
        HTTPException=HTTPException,
        BackgroundTasks=BackgroundTasks,
        BulkAssignSegmentsRequest=BulkAssignSegmentsRequest,
        TranscriptSegment=TranscriptSegment,
        Depends=Depends,
        auth=SimpleNamespace(get_current_user_uid=lambda: 'u'),
        deserialize_conversation=lambda raw: SimpleNamespace(
            transcript_segments=[TranscriptSegment(**s) for s in raw['transcript_segments']]
        ),
        _drop_display_projection=Mock(),
        _emit_speaker_identity_confirmed=Mock(),
        _speaker_assignment=lambda segment: str(segment.person_id),
    )
    load_functions(BACKEND / 'routers/conversations.py', {'_assign_manual_speaker', 'assign_segments_bulk'}, namespace)
    request = BulkAssignSegmentsRequest(segment_ids=['s1'], assign_type='not_a_person')
    for _ in range(2):  # Already excluded is a successful repeat decision.
        tasks = BackgroundTasks()
        response = namespace['assign_segments_bulk']('conversation', request, tasks, uid='u')
        assert len(response.transcript_segments) == 3  # Exclusion retains the transcript.
        assert tasks.tasks == []
        assert all(
            not s.is_user and s.person_id is None and s.speaker_label_source is None
            for s in response.transcript_segments[:2]
        )
        assert 4 in manual_rejected_speakers(raw['manual_speaker_assignments'])
        assert '4' in _manually_decided(raw)[0]
        assert receipt_person_ids(raw['manual_speaker_assignments']) == []
        assert assignment_evidence(raw['transcript_segments'][:2], person_id=None, source='manual') == {}
        future = apply_manual_assignments(
            [{'id': 'later', 'speaker_id': 4, 'is_user': True, 'person_id': None}], raw['manual_speaker_assignments']
        )[0]
        assert future['is_user'] is False and future['person_id'] is None
    # Each live exclusion records the same ignored-voice marker the reject route
    # and tag-prompt answers write, fenced by the assignment generation.
    ignored.assert_has_calls(
        [
            call('u', 'conversation', 4, ANY, assignment_generation=1),
            call('u', 'conversation', 4, ANY, assignment_generation=2),
        ]
    )
    assert ignored.call_count == 2
    cleared.assert_not_called()
    learning.assert_not_called()
    for assign_type, value in (('person_id', 'p1'), ('is_user', 'true')):
        # Drive the router path: a positive bulk assignment must retire the
        # ignored-voice marker that the earlier exclusion recorded.
        positive = BulkAssignSegmentsRequest(segment_ids=['s1'], assign_type=assign_type, value=value)
        response = namespace['assign_segments_bulk']('conversation', positive, BackgroundTasks(), uid='u')
        assert response.transcript_segments[0].person_id == ('p1' if assign_type == 'person_id' else None)
        assert response.transcript_segments[0].is_user is (assign_type == 'is_user')
    # Replacing the exclusion with a person/user assignment retires the
    # ignored-voice marker: the voice leaves Ignored Voices and matching again.
    cleared.assert_has_calls(
        [
            call('u', 'conversation', [4], assignment_generation=3),
            call('u', 'conversation', [4], assignment_generation=4),
        ]
    )
    assert cleared.call_count == 2
    learning.assert_not_called()


def test_range_reassignment_keeps_a_winning_whole_voice_rejection_restorable():
    """A range-only positive entry (segment_only) does not unseat the whole-voice
    not_a_person rejection, so it must not clear the ignored-voice marker."""
    raw = {
        'id': 'conversation',
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 4, 'is_user': False, 'person_id': None, 'start': 0, 'end': 2, 'text': 'TV'},
            {'id': 's2', 'speaker_id': 4, 'is_user': False, 'person_id': None, 'start': 2, 'end': 4, 'text': 'movie'},
        ],
    }
    cleared = Mock()
    ignored = Mock()
    namespace = dict(
        Optional=Optional,
        List=list,
        Sequence=list,
        Mapping=dict,
        Any=object,
        datetime=__import__('datetime').datetime,
        timezone=__import__('datetime').timezone,
        Depends=Depends,
        HTTPException=HTTPException,
        BackgroundTasks=BackgroundTasks,
        BulkAssignSegmentsRequest=BulkAssignSegmentsRequest,
        TranscriptSegment=TranscriptSegment,
        auth=SimpleNamespace(get_current_user_uid=lambda: 'u'),
        deserialize_conversation=lambda raw: SimpleNamespace(
            transcript_segments=[TranscriptSegment(**s) for s in raw['transcript_segments']]
        ),
        _drop_display_projection=Mock(),
        _emit_speaker_identity_confirmed=Mock(),
        _speaker_assignment=lambda segment: str(segment.person_id),
        voice_profiles_db=SimpleNamespace(record_ignored_voice=ignored, clear_ignored_voices=cleared),
        record_exclusion_markers=lambda uid, cid, raw, resolved, **kwargs: record_exclusion_markers(
            uid, cid, raw, resolved, voice_profiles=SimpleNamespace(record_ignored_voice=ignored), **kwargs
        ),
        retire_exclusion_markers=lambda uid, cid, raw, resolved, **kwargs: retire_exclusion_markers(
            uid, cid, raw, resolved, voice_profiles=SimpleNamespace(clear_ignored_voices=cleared), **kwargs
        ),
        manual_rejected_speakers=manual_rejected_speakers,
        teaching_segment_ids=lambda segments, resolved: resolved,
        delete_speech_profile_blob=Mock(),
        run_authorized_person_learning=Mock(),
        run_authorized_owner_learning=Mock(),
    )

    def assign(uid, conversation_id, **kwargs):
        before = list(raw['transcript_segments'])
        segments, receipt, resolved, previous = manual_assignment(raw, **kwargs)
        raw.update(transcript_segments=segments, manual_speaker_assignments=receipt)
        return raw, resolved, [], before

    namespace['conversations_db'] = SimpleNamespace(assign_conversation_speaker=assign)
    load_functions(
        BACKEND / 'utils/speaker_assignment_teaching.py',
        {'commit_manual_assignment', 'schedule_assignment_teaching'},
        namespace,
    )
    load_functions(BACKEND / 'routers/conversations.py', {'_assign_manual_speaker', 'assign_segments_bulk'}, namespace)
    # Whole-voice exclusion first (no segment ids: speaker-scoped path).
    exclusion = BulkAssignSegmentsRequest(segment_ids=['s1', 's2'], assign_type='not_a_person')
    namespace['assign_segments_bulk']('conversation', exclusion, BackgroundTasks(), uid='u')
    assert 4 in manual_rejected_speakers(raw['manual_speaker_assignments'])
    ignored.assert_called_once()
    # Range-only positive reassignment: still rejected per the receipt, so the
    # marker survives (restorable from Settings > Ignored Voices).
    kwargs = dict(uid='u', background_tasks=BackgroundTasks(), speaker_id=4, time_range=(0.0, 2.0))
    namespace['_assign_manual_speaker']('conversation', 'person_id', 'p1', **kwargs)
    assert 4 in manual_rejected_speakers(raw['manual_speaker_assignments'])
    cleared.assert_not_called()


def test_marker_store_failure_after_commit_still_reports_the_exclusion_saved():
    """A marker write/clear failure after the assignment committed must not
    500 the endpoint: the exclusion (or positive assignment) is already durable,
    so the response stays authoritative instead of reporting it unsaved."""
    raw = {
        'id': 'conversation',
        'transcript_segments': [
            {'id': 's1', 'speaker_id': 4, 'is_user': True, 'person_id': None, 'start': 0, 'end': 2, 'text': 'TV'},
        ],
    }

    def build_controller(ignored, cleared):
        namespace = dict(
            Optional=Optional,
            List=list,
            Sequence=list,
            Mapping=dict,
            Any=object,
            datetime=__import__('datetime').datetime,
            timezone=__import__('datetime').timezone,
            logger=Mock(),
            voice_profiles_db=SimpleNamespace(record_ignored_voice=ignored, clear_ignored_voices=cleared),
            record_exclusion_markers=lambda uid, cid, raw, resolved, **kwargs: record_exclusion_markers(
                uid, cid, raw, resolved, voice_profiles=SimpleNamespace(record_ignored_voice=ignored), **kwargs
            ),
            retire_exclusion_markers=lambda uid, cid, raw, resolved, **kwargs: retire_exclusion_markers(
                uid, cid, raw, resolved, voice_profiles=SimpleNamespace(clear_ignored_voices=cleared), **kwargs
            ),
            manual_rejected_speakers=manual_rejected_speakers,
            teaching_segment_ids=lambda segments, resolved: resolved,
            delete_speech_profile_blob=Mock(),
            run_authorized_person_learning=Mock(),
            run_authorized_owner_learning=Mock(),
        )

        def assign(uid, conversation_id, **kwargs):
            before = list(raw['transcript_segments'])
            segments, receipt, resolved, previous = manual_assignment(raw, **kwargs)
            raw.update(transcript_segments=segments, manual_speaker_assignments=receipt)
            return raw, resolved, [], before

        namespace['conversations_db'] = SimpleNamespace(assign_conversation_speaker=assign)
        load_functions(
            BACKEND / 'utils/speaker_assignment_teaching.py',
            {'commit_manual_assignment', 'schedule_assignment_teaching'},
            namespace,
        )
        namespace.update(
            HTTPException=HTTPException,
            BackgroundTasks=BackgroundTasks,
            BulkAssignSegmentsRequest=BulkAssignSegmentsRequest,
            TranscriptSegment=TranscriptSegment,
            Depends=Depends,
            auth=SimpleNamespace(get_current_user_uid=lambda: 'u'),
            deserialize_conversation=lambda raw: SimpleNamespace(
                transcript_segments=[TranscriptSegment(**s) for s in raw['transcript_segments']]
            ),
            _drop_display_projection=Mock(),
            _emit_speaker_identity_confirmed=Mock(),
            _speaker_assignment=lambda segment: str(segment.person_id),
        )
        load_functions(
            BACKEND / 'routers/conversations.py', {'_assign_manual_speaker', 'assign_segments_bulk'}, namespace
        )
        return namespace

    def boom(*args, **kwargs):
        raise RuntimeError('state store unavailable')

    # Exclusion: the marker write fails after commit; the route must not raise.
    namespace = build_controller(ignored=boom, cleared=Mock())
    exclusion = BulkAssignSegmentsRequest(segment_ids=['s1'], assign_type='not_a_person')
    response = namespace['assign_segments_bulk']('conversation', exclusion, BackgroundTasks(), uid='u')
    assert response.transcript_segments[0].person_id is None
    assert 4 in manual_rejected_speakers(raw['manual_speaker_assignments'])

    # Positive reassignment: the marker clear fails after commit; still no raise.
    namespace = build_controller(ignored=Mock(), cleared=boom)
    positive = BulkAssignSegmentsRequest(segment_ids=['s1'], assign_type='person_id', value='p1')
    response = namespace['assign_segments_bulk']('conversation', positive, BackgroundTasks(), uid='u')
    assert response.transcript_segments[0].person_id == 'p1'
    assert 4 not in manual_rejected_speakers(raw['manual_speaker_assignments'])
