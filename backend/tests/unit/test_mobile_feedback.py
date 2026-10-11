from __future__ import annotations

import pytest

from tests.unit.fixtures.generic_firestore_fake import FakeFirestore
from models.feedback import FeedbackSurface, FeedbackTargetKind, MobileFeedbackKind, MobileFeedbackRequest
from database import feedback as feedback_db
from routers import mobile_feedback


def test_mobile_feedback_request_rejects_cross_surface_reason():
    with pytest.raises(ValueError):
        MobileFeedbackRequest(
            feedback_id='f-1',
            kind=MobileFeedbackKind.summary_helpfulness,
            target_id='conversation-1',
            value=-1,
            reason='recording_missing_audio',
        )


def test_mobile_feedback_request_rejects_summary_recording_target_kind():
    with pytest.raises(ValueError):
        MobileFeedbackRequest(
            feedback_id='f-target-kind',
            kind=MobileFeedbackKind.summary_helpfulness,
            target_kind='recording',
            target_id='conversation-1',
            value=1,
        )


def test_idempotent_feedback_create_and_replay(monkeypatch):
    firestore = FakeFirestore()
    monkeypatch.setattr(feedback_db, 'get_firestore_client', lambda: firestore)

    first = feedback_db.record_feedback_event_idempotent(
        'uid-1',
        FeedbackSurface.recording_quality,
        FeedbackTargetKind.recording,
        'recording-1',
        -1,
        feedback_id='client-f-1',
        feedback_kind=MobileFeedbackKind.recording_quality,
        reason='recording_missing_audio',
        app_version='1.2.3',
        app_build='123',
        platform='ios',
    )
    replay = feedback_db.record_feedback_event_idempotent(
        'uid-1',
        FeedbackSurface.recording_quality,
        FeedbackTargetKind.recording,
        'recording-1',
        -1,
        feedback_id='client-f-1',
        feedback_kind=MobileFeedbackKind.recording_quality,
        reason='recording_missing_audio',
        app_version='1.2.3',
        app_build='123',
        platform='ios',
    )
    assert first[1] is True
    assert replay == (first[0], False)
    assert len(firestore.docs) == 1


def test_idempotent_feedback_normalizes_whitespace_comment_on_create_and_replay(monkeypatch):
    firestore = FakeFirestore()
    monkeypatch.setattr(feedback_db, 'get_firestore_client', lambda: firestore)

    first = feedback_db.record_feedback_event_idempotent(
        'uid-1',
        FeedbackSurface.conversation_summary,
        FeedbackTargetKind.conversation,
        'conversation-1',
        -1,
        feedback_id='client-f-whitespace',
        feedback_kind=MobileFeedbackKind.summary_helpfulness,
        comment='   ',
    )
    replay = feedback_db.record_feedback_event_idempotent(
        'uid-1',
        FeedbackSurface.conversation_summary,
        FeedbackTargetKind.conversation,
        'conversation-1',
        -1,
        feedback_id='client-f-whitespace',
        feedback_kind=MobileFeedbackKind.summary_helpfulness,
        comment='   ',
    )
    assert first[1] is True
    assert replay == (first[0], False)
    assert 'comment' not in next(iter(firestore.docs.values()))


def test_idempotency_key_cannot_change_target_or_value(monkeypatch):
    firestore = FakeFirestore()
    monkeypatch.setattr(feedback_db, 'get_firestore_client', lambda: firestore)
    kwargs = dict(
        uid='uid-1',
        surface=FeedbackSurface.conversation_summary,
        target_kind=FeedbackTargetKind.conversation,
        value=1,
        feedback_id='client-f-2',
    )
    feedback_db.record_feedback_event_idempotent(target_id='conversation-1', **kwargs)
    with pytest.raises(feedback_db.FeedbackIdempotencyConflict):
        feedback_db.record_feedback_event_idempotent(target_id='conversation-2', **kwargs)


def test_legacy_best_effort_writer_still_accepts_new_metadata(monkeypatch):
    firestore = FakeFirestore()
    monkeypatch.setattr(feedback_db, 'get_firestore_client', lambda: firestore)
    event_id = feedback_db.record_feedback_event(
        'uid-1',
        FeedbackSurface.conversation_summary,
        FeedbackTargetKind.conversation,
        'conversation-1',
        -1,
        reason='summary_inaccurate',
        feedback_kind=MobileFeedbackKind.summary_helpfulness,
        backend_release='release-1',
        model_name='summary-model',
    )
    assert event_id is not None
    row = next(iter(firestore.docs.values()))
    assert row['feedback_kind'] == 'summary_helpfulness'
    assert row['backend_release'] == 'release-1'
    assert row['model_name'] == 'summary-model'


def test_mobile_feedback_route_checks_summary_ownership_and_emits_after_durable_write(monkeypatch):
    payload = MobileFeedbackRequest(
        feedback_id='client-f-3',
        kind=MobileFeedbackKind.summary_helpfulness,
        target_id='conversation-1',
        value=-1,
        reason='summary_inaccurate',
        app_version='1.0.522+240',
        client_app_namespace='com.friend.ios',
        client_app_profile='production',
    )
    monkeypatch.setattr(mobile_feedback.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid})
    recorded = {}
    monkeypatch.setattr(
        mobile_feedback.feedback_db,
        'record_feedback_event_idempotent',
        lambda *args, **kwargs: recorded.update(kwargs) or ('event-1', True),
    )
    emitted = []
    monkeypatch.setattr(mobile_feedback, 'emit_product_event', lambda **kwargs: emitted.append(kwargs))

    receipt = mobile_feedback.submit_mobile_feedback(payload, 'ios', None, None, 'uid-1')
    assert receipt.persisted is True
    assert receipt.created is True
    assert recorded['app_version'] == '1.0.522+240'
    assert recorded['app_build'] == '240'
    assert recorded['platform'] == 'ios'
    assert recorded['client_app_namespace'] == 'com.friend.ios'
    assert recorded['client_app_profile'] == 'production'
    assert emitted[0]['event'] == 'Product Feedback Submitted'


def test_mobile_feedback_route_rejects_unowned_recording(monkeypatch):
    payload = MobileFeedbackRequest(
        feedback_id='client-f-4',
        kind=MobileFeedbackKind.recording_quality,
        target_kind='recording',
        target_id='recording-1',
        value=1,
    )
    monkeypatch.setattr(mobile_feedback.recording_sessions_db, 'get_recording_session', lambda uid, sid: None)
    with pytest.raises(Exception) as error:
        mobile_feedback.submit_mobile_feedback(payload, None, None, None, 'uid-1')
    assert getattr(error.value, 'status_code', None) == 404


def test_recording_quality_accepts_owned_conversation_fallback_for_legacy_detail_page(monkeypatch):
    payload = MobileFeedbackRequest(
        feedback_id='client-f-conversation-recording',
        kind=MobileFeedbackKind.recording_quality,
        target_id='conversation-1',
        value=1,
    )
    monkeypatch.setattr(mobile_feedback.recording_sessions_db, 'get_recording_session', lambda uid, sid: None)
    monkeypatch.setattr(mobile_feedback.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid})
    recorded = {}
    monkeypatch.setattr(
        mobile_feedback.feedback_db,
        'record_feedback_event_idempotent',
        lambda *args, **kwargs: recorded.update(args=args, kwargs=kwargs) or ('event-1', True),
    )
    monkeypatch.setattr(mobile_feedback, 'emit_product_event', lambda **kwargs: None)

    receipt = mobile_feedback.submit_mobile_feedback(payload, None, None, None, 'uid-1')

    assert receipt.persisted is True
    assert recorded['args'][2] == FeedbackTargetKind.conversation
    assert recorded['kwargs']['related_conversation_id'] == 'conversation-1'


def test_recording_quality_explicit_conversation_target_skips_recording_lookup(monkeypatch):
    payload = MobileFeedbackRequest(
        feedback_id='client-f-explicit-conversation',
        kind=MobileFeedbackKind.recording_quality,
        target_kind='conversation',
        target_id='conversation-1',
        value=1,
    )
    monkeypatch.setattr(
        mobile_feedback.recording_sessions_db,
        'get_recording_session',
        lambda uid, sid: pytest.fail('explicit conversation target must not query recording ownership'),
    )
    monkeypatch.setattr(mobile_feedback.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid})
    recorded = {}
    monkeypatch.setattr(
        mobile_feedback.feedback_db,
        'record_feedback_event_idempotent',
        lambda *args, **kwargs: recorded.update(args=args, kwargs=kwargs) or ('event-1', True),
    )
    monkeypatch.setattr(mobile_feedback, 'emit_product_event', lambda **kwargs: None)

    mobile_feedback.submit_mobile_feedback(payload, None, None, None, 'uid-1')
    assert recorded['args'][2] == FeedbackTargetKind.conversation


def test_recording_quality_explicit_recording_target_does_not_fallback_to_conversation(monkeypatch):
    payload = MobileFeedbackRequest(
        feedback_id='client-f-explicit-recording',
        kind=MobileFeedbackKind.recording_quality,
        target_kind='recording',
        target_id='conversation-1',
        value=1,
    )
    monkeypatch.setattr(mobile_feedback.recording_sessions_db, 'get_recording_session', lambda uid, sid: None)
    monkeypatch.setattr(mobile_feedback.conversations_db, 'get_conversation', lambda uid, cid: {'id': cid})
    with pytest.raises(Exception) as error:
        mobile_feedback.submit_mobile_feedback(payload, None, None, None, 'uid-1')
    assert getattr(error.value, 'status_code', None) == 404
