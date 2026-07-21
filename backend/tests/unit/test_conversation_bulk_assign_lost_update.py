"""Regression: PATCH /v1/conversations/{id}/segments/assign-bulk must persist the assignment as a
transactional read-modify-write by segment id, not a whole-array overwrite of a snapshot read
outside the transaction. Otherwise a concurrent segment edit that commits between the handler's read
and its write is silently lost.

The real ``assign_segments_bulk`` handler is exercised; only the database seam
(``conversations_db``) and the snapshot deserialization are faked. The stateful fake models the two
persistence primitives' real semantics — ``update_conversation_segments`` overwrites
``transcript_segments`` wholesale, ``bulk_assign_segment_speakers`` re-reads current state and
applies by id — plus a concurrent edit that lands right after the handler's read.
"""

import copy
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import BackgroundTasks

import routers.conversations as convo_router
from models.conversation import BulkAssignSegmentsRequest


class _Seg:
    """Minimal transcript-segment stand-in with the attributes the handler touches."""

    def __init__(self, sid, text, is_user=False, person_id=None):
        self.id = sid
        self.text = text
        self.is_user = is_user
        self.person_id = person_id

    def model_dump(self):
        return {'id': self.id, 'text': self.text, 'is_user': self.is_user, 'person_id': self.person_id}


def _run(assign_type, value):
    # Authoritative DB state, keyed by segment id.
    db_state = {
        'transcript_segments': [
            {'id': 's1', 'text': 'original one', 'is_user': False, 'person_id': None},
            {'id': 's2', 'text': 'second', 'is_user': False, 'person_id': None},
        ]
    }

    def fake_get_valid(_uid, cid):
        return {'id': cid}  # opaque; deserialize is faked below

    def fake_deserialize(_conv):
        # The handler reads its working snapshot here.
        snapshot = [_Seg(s['id'], s['text'], s['is_user'], s['person_id']) for s in db_state['transcript_segments']]
        # A concurrent writer commits an edit to s1 right after the handler's read, before it persists.
        for s in db_state['transcript_segments']:
            if s['id'] == 's1':
                s['text'] = 'edited by other writer'
        return SimpleNamespace(transcript_segments=snapshot)

    # OLD path: whole-array overwrite with the caller's (now stale) array.
    def fake_update_conversation_segments(_uid, _cid, segments, *a, **k):
        db_state['transcript_segments'] = copy.deepcopy(segments)
        return True

    # NEW path: transactional read-modify-write by id against CURRENT state.
    def fake_bulk_assign(_uid, _cid, segment_ids, atype, val):
        target = set(segment_ids)
        found = False
        for seg in db_state['transcript_segments']:
            if seg['id'] not in target:
                continue
            if atype == 'is_user':
                seg['is_user'] = bool(val) if val is not None else False
                seg['person_id'] = None
                found = True
            elif atype == 'person_id':
                seg['is_user'] = False
                seg['person_id'] = val
                found = True
        return 'ok' if found else 'segment_not_found'

    with patch.object(convo_router, '_get_valid_conversation_by_id', fake_get_valid), patch.object(
        convo_router, 'deserialize_conversation', fake_deserialize
    ), patch.object(
        convo_router.conversations_db, 'update_conversation_segments', fake_update_conversation_segments
    ), patch.object(
        convo_router.conversations_db, 'bulk_assign_segment_speakers', fake_bulk_assign, create=True
    ):
        req = BulkAssignSegmentsRequest(segment_ids=['s2'], assign_type=assign_type, value=value)
        convo_router.assign_segments_bulk(conversation_id='c1', data=req, background_tasks=BackgroundTasks(), uid='u1')

    return {s['id']: s for s in db_state['transcript_segments']}


def test_bulk_assign_does_not_clobber_concurrent_segment_edit():
    by_id = _run(assign_type='person_id', value='person-42')
    # The requested assignment landed on s2.
    assert by_id['s2']['person_id'] == 'person-42'
    assert by_id['s2']['is_user'] is False
    # And the concurrent edit to s1 survived (was not overwritten by the stale snapshot array).
    assert by_id['s1']['text'] == 'edited by other writer'


def test_bulk_assign_is_user_also_survives_concurrent_edit():
    by_id = _run(assign_type='is_user', value='true')
    assert by_id['s2']['is_user'] is True
    assert by_id['s2']['person_id'] is None
    assert by_id['s1']['text'] == 'edited by other writer'
