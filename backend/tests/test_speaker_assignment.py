"""Bulk media exclusion uses the persisted manual decision, without voice learning.

Load the route's functions without initializing unrelated provider clients. The
assignment policy and teaching scheduler remain the production implementations.
"""

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import Mock

from fastapi import BackgroundTasks, Depends, HTTPException
from models.conversation import BulkAssignSegmentsRequest
from models.transcript_segment import TranscriptSegment
from utils.manual_speaker_assignments import manual_assignment, apply_manual_assignments, manual_rejected_speakers
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
    namespace = dict(
        Optional=Optional,
        List=list,
        Sequence=list,
        Mapping=dict,
        Any=object,
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
    learning.assert_not_called()
    for person_id, is_user in [('p1', False), (None, True)]:
        segments, receipt, _, _ = manual_assignment(raw, person_id=person_id, is_user=is_user, speaker_id=4)
        assert manual_rejected_speakers(receipt) == {}
        assert all(s['person_id'] == person_id and s['is_user'] == is_user for s in segments[:2])
