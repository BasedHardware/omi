import sys
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import routers.conversations as conv_router
from utils.conversations.process_conversation import AppUsageAttribution


def _app(*, app_id='summary-app', summarizes=True, disabled=False):
    return SimpleNamespace(
        id=app_id,
        disabled=disabled,
        works_with_memories=lambda: summarizes,
    )


def _route_context(*, raw_app, available_app, enabled):
    conversation = {'id': 'c1', 'status': 'completed'}
    model = SimpleNamespace(language='en')
    return (
        model,
        patch.object(conv_router, '_get_valid_conversation_by_id', return_value=conversation),
        patch.object(conv_router.conversations_db, 'is_soft_deleted', return_value=False),
        patch.object(conv_router, 'deserialize_conversation', return_value=model),
        # Patched at their source modules, not on the router: the validator imports these
        # inside the function so the isolation seam can load this router without the apps
        # chain (see the comment at _validate_reprocess_app_selection).
        patch('database.apps.get_app_by_id_db', return_value=raw_app),
        patch('utils.apps.get_available_app_model_by_id', return_value=available_app),
        patch('utils.apps.is_user_app_enabled', return_value=enabled),
        patch.object(conv_router, 'process_conversation', return_value=model),
    )


@pytest.mark.parametrize(
    ('app_id', 'raw_app', 'available_app', 'enabled', 'status_code', 'detail'),
    [
        ('missing-app', None, None, False, 404, 'App not found'),
        ('private-app', {'id': 'private-app'}, None, True, 403, 'App is not available to this user'),
        (
            'chat-app',
            {'id': 'chat-app'},
            _app(app_id='chat-app', summarizes=False),
            True,
            400,
            'App does not support conversation summarization',
        ),
        (
            'disabled-app',
            {'id': 'disabled-app'},
            _app(app_id='disabled-app', disabled=True),
            True,
            409,
            'App is currently unavailable',
        ),
        (
            'summary-app',
            {'id': 'summary-app'},
            _app(),
            False,
            409,
            'App must be enabled before it can summarize a conversation',
        ),
    ],
)
def test_explicit_app_rejections_are_client_errors_before_processing(
    app_id, raw_app, available_app, enabled, status_code, detail
):
    model, p1, p2, p3, p4, p5, p6, process_patch = _route_context(
        raw_app=raw_app,
        available_app=available_app,
        enabled=enabled,
    )
    with p1, p2, p3, p4, p5, p6, process_patch as process:
        with pytest.raises(HTTPException) as exc:
            conv_router.reprocess_conversation(conversation_id='c1', app_id=app_id, uid='u1')

    assert exc.value.status_code == status_code
    assert exc.value.detail == detail
    process.assert_not_called()


def test_plain_regenerate_still_succeeds_without_app_validation():
    model, p1, p2, p3, p4, p5, p6, process_patch = _route_context(
        raw_app=None,
        available_app=None,
        enabled=False,
    )
    with p1, p2, p3, p4 as raw_lookup, p5 as available_lookup, p6 as enabled_lookup, process_patch as process:
        result = conv_router.reprocess_conversation(conversation_id='c1', uid='u1')

    assert result is model
    raw_lookup.assert_not_called()
    available_lookup.assert_not_called()
    enabled_lookup.assert_not_called()
    assert process.call_args.kwargs['app_id'] is None
    assert process.call_args.kwargs['explicit_app'] is None
    assert process.call_args.kwargs['app_usage_attribution'] is AppUsageAttribution.NON_USER_REPROCESS


def test_valid_explicit_selection_reaches_processing_with_explicit_attribution():
    selected = _app()
    model, p1, p2, p3, p4, p5, p6, process_patch = _route_context(
        raw_app={'id': selected.id},
        available_app=selected,
        enabled=True,
    )
    with p1, p2, p3, p4, p5, p6, process_patch as process:
        result = conv_router.reprocess_conversation(conversation_id='c1', app_id=selected.id, uid='u1')

    assert result is model
    assert process.call_args.kwargs['app_id'] == selected.id
    assert process.call_args.kwargs['explicit_app'] is selected
    assert process.call_args.kwargs['app_usage_attribution'] is AppUsageAttribution.EXPLICIT_SELECTION


@pytest.mark.parametrize('partial_proactive_engine', [False, True])
def test_lazy_enrichment_uses_non_user_usage_attribution(monkeypatch, partial_proactive_engine):
    conversation = {'id': 'c1', 'deferred': True}
    model = SimpleNamespace(language='en', deferred=True)
    monkeypatch.setattr(conv_router.lifecycle_service, 'reacquire_deferred_processing', lambda *_args: True)
    monkeypatch.setattr(
        conv_router.lifecycle_service, 'processing_admission_guard', lambda *_args, **_kwargs: nullcontext()
    )
    monkeypatch.setattr(conv_router, 'deserialize_conversation', lambda _conversation: model)
    monkeypatch.setattr(conv_router, 'submit_with_context', lambda _executor, function: function())
    if partial_proactive_engine:
        # CI reproduced this: the file-backed module was already in sys.modules
        # without persist_desktop_meeting_arrival_best_effort (circular import
        # left it partially initialized). monkeypatch.setattr raising=True then
        # fails before the route is exercised.
        partial = ModuleType('utils.task_intelligence.proactive_engine')
        partial.__file__ = 'partial-proactive-engine'
        monkeypatch.setitem(sys.modules, 'utils.task_intelligence.proactive_engine', partial)
    # create=True binds the in-function import seam whether or not that name
    # already exists on the cached module.
    with patch(
        'utils.task_intelligence.proactive_engine.persist_desktop_meeting_arrival_best_effort',
        create=True,
    ), patch.object(conv_router, 'process_conversation', return_value=model) as process:
        result = conv_router._enrich_deferred_conversation('u1', conversation)

    assert result['deferred'] is False
    assert process.call_args.kwargs['is_reprocess'] is False
    assert process.call_args.kwargs['app_usage_attribution'] is AppUsageAttribution.NON_USER_REPROCESS
