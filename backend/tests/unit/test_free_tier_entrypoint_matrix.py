"""Every coordinator entrypoint retains capped text and projection without derived work.

This calls the coordinator with the production trigger/observer arguments. Real
HTTP ingress, hash binding and transaction races live in the projection suites.
"""

from datetime import datetime, timezone
from unittest.mock import Mock
from typing import Any

import pytest
from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from models.client_processing import ClientProcessing, ProjectedStructure, ProjectionProvenance
from utils.conversations import process_conversation as pc
from utils.conversations.processing_trigger import ProcessingTrigger

_ENTRIES: list[dict[str, Any]] = [
    {
        'id': 'conversations_enrich_187',
        'label': (
            'routers/conversations.py:187 _enrich_deferred_conversation '
            '(coordinator-with-exact-args; trigger=FIRST_OPEN)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.FIRST_OPEN},
        'attribution': 'non_user_reprocess',
    },
    {
        'id': 'conversations_create_351',
        'label': (
            'routers/conversations.py:351 process_in_progress_conversation '
            '(coordinator-with-exact-args; POST /v1/conversations trigger=CLIENT_FINALIZE)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.CLIENT_FINALIZE},
        'observer': True,
    },
    {
        'id': 'conversations_reprocess_495',
        'label': (
            'routers/conversations.py:495 reprocess_conversation '
            '(coordinator-with-exact-args; trigger=USER_REPROCESS)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.USER_REPROCESS},
        'attribution': 'non_user_reprocess',
    },
    {
        'id': 'developer_text_1500',
        'label': (
            'routers/developer.py:1500 create-from-text '
            '(coordinator-with-exact-args; source=external_integration, §1.2 non-desktop)'
        ),
        'kind': 'external',
        'source': ConversationSource.external_integration,
        'kwargs': {},
    },
    {
        'id': 'developer_from_segments_1776',
        'label': (
            'routers/developer.py:2142 from-segments '
            '(coordinator-with-exact-args; default source=phone, trigger=CLIENT_FINALIZE, §1.2 non-desktop)'
        ),
        'kind': 'create',
        'source': ConversationSource.phone,
        'kwargs': {'trigger': ProcessingTrigger.CLIENT_FINALIZE},
    },
    {
        'id': 'developer_from_segments_desktop',
        'label': (
            'routers/developer.py:2142 from-segments desktop '
            '(coordinator-with-exact-args; a client-uploaded final transcript runs as '
            'trigger=CLIENT_FINALIZE, so the freemium desktop capture deferral must not store the placeholder)'
        ),
        'kind': 'create',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.CLIENT_FINALIZE},
    },
    {
        'id': 'listen_157_via_finalizer_137',
        'label': (
            'routers/listen/conversations.py:157 → finalizer.py:137 '
            '(coordinator-with-exact-args; listen enqueues, cannot drive WS hermetically; '
            'source=desktop is a supported listen source at conversations.py:318; '
            'trigger=CAPTURE_END, defer_derived_effects=True)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.CAPTURE_END, 'defer_derived_effects': True},
        'observer': True,
        'derived_observer': True,
    },
    {
        'id': 'merge_354_omi',
        'label': (
            'utils/conversations/merge_conversations.py:354 '
            '(coordinator-with-exact-args; trigger=MERGE; '
            'source from earliest conv :269 default omi — §1.2 non-desktop process_normally)'
        ),
        'kind': 'existing',
        'source': ConversationSource.omi,
        'kwargs': {'trigger': ProcessingTrigger.MERGE},
        'scenario': 'merge',
    },
    {
        'id': 'merge_354_desktop',
        'label': (
            'utils/conversations/merge_conversations.py:354 '
            '(coordinator-with-exact-args; trigger=MERGE; '
            'source from earliest conv :269 desktop — at cap remains budget waiting)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.MERGE},
        'scenario': 'merge',
    },
    {
        # The postprocess_conversation.py:164 row this replaces cited a module
        # deleted from main by a7bc5fd0c2. routers/integration.py:173 is the
        # live call site that was missing from the matrix entirely (the matrix
        # must see it even though it is safe today only because the route
        # forces source=external_integration).
        'id': 'integration_173',
        'label': (
            'routers/integration.py:173 external-integration capture '
            '(coordinator-with-exact-args; route forces source=external_integration '
            ':165, no extra kwargs; replaces the postprocess_conversation.py:164 '
            'row — module deleted by a7bc5fd0c2)'
        ),
        'kind': 'external',
        'source': ConversationSource.external_integration,
        'kwargs': {},
    },
    {
        'id': 'sync_reprocess_785_omi',
        'label': (
            'utils/sync/pipeline.py:785 _reprocess_conversation_after_update '
            '(coordinator-with-exact-args; trigger=SYNC_UPDATE; '
            'source carried from the stored conversation, default omi — §1.2 non-desktop)'
        ),
        'kind': 'existing',
        'source': ConversationSource.omi,
        'kwargs': {'trigger': ProcessingTrigger.SYNC_UPDATE},
        'observer': True,
        'scenario': 'sync',
    },
    {
        'id': 'sync_reprocess_785_desktop',
        'label': (
            'utils/sync/pipeline.py:785 _reprocess_conversation_after_update '
            '(coordinator-with-exact-args; trigger=SYNC_UPDATE; '
            'source carried from the stored conversation — desktop at cap → budget waiting)'
        ),
        'kind': 'existing',
        'source': ConversationSource.desktop,
        'kwargs': {'trigger': ProcessingTrigger.SYNC_UPDATE},
        'observer': True,
        'scenario': 'sync',
    },
    {
        'id': 'sync_create_1179_omi',
        'label': (
            'utils/sync/pipeline.py:1179 process_segment create '
            '(coordinator-with-exact-args; source= parameter :1051 default omi — §1.2 non-desktop)'
        ),
        'kind': 'create',
        'source': ConversationSource.omi,
        'kwargs': {},
        'observer': True,
        'scenario': 'sync',
    },
    {
        'id': 'sync_create_1179_desktop',
        'label': (
            'utils/sync/pipeline.py:1179 process_segment create '
            '(coordinator-with-exact-args; source= parameter :1051 carried onto CreateConversation :1172; '
            'desktop sync at cap → budget waiting)'
        ),
        'kind': 'create',
        'source': ConversationSource.desktop,
        'kwargs': {},
        'observer': True,
        'scenario': 'sync',
    },
]


@pytest.mark.parametrize('entry', _ENTRIES, ids=lambda entry: entry['id'])
@pytest.mark.parametrize('summary_enabled', [True, False])
@pytest.mark.parametrize('has_summary', [True, False])
def test_capped_entrypoint_preserves_backlog_without_model_or_derived_work(
    monkeypatch, entry, summary_enabled, has_summary
):
    monkeypatch.setenv('CLIENT_SUMMARIES_AT_CAP_ENABLED', 'true' if summary_enabled else 'false')
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda uid, lane=None: True)
    monkeypatch.setattr(pc.funded_processing, 'processing_allowed', lambda uid: False)
    now = datetime.now(timezone.utc)
    fields = dict(
        source=entry['source'],
        started_at=now,
        finished_at=now,
        transcript_segments=[TranscriptSegment(is_user=True, text='Captured words remain', start=0, end=1)],
    )
    if entry['kind'] == 'create':
        incoming = CreateConversation(**fields)
    elif entry['kind'] == 'external':
        incoming = ExternalIntegrationCreateConversation(text='Captured integration words', **fields)
    else:
        incoming = Conversation(id='existing', created_at=now, structured=Structured(), status='processing', **fields)
    projection = (
        ClientProcessing(
            schema_version=1,
            transcript_sha256='ab' * 32,
            structure=ProjectedStructure(title='Untrusted local summary'),
            provenance=ProjectionProvenance(model_id='afm', runtime='local', device_class='mac', generated_at=now),
        )
        if has_summary
        else None
    )
    create, persist = Mock(return_value=True), Mock(return_value=True)
    monkeypatch.setattr(pc.lifecycle_service, 'create_completed_conversation', create)
    monkeypatch.setattr(pc.lifecycle_service, 'persist_processed_conversation', persist)
    forbidden = Mock(side_effect=AssertionError('capped work launched an effect'))
    for name in (
        '_get_structured',
        '_extract_memories',
        '_save_action_items',
        'trigger_conversation_apps',
        'assign_conversation_to_folder',
        'submit_with_context',
        '_enrich_meeting_context',
    ):
        monkeypatch.setattr(pc, name, forbidden)
    owned, dispositions, runners = [], [], []
    result = pc.process_conversation(
        'synthetic',
        'en',
        incoming,
        **entry['kwargs'],
        client_projection=projection,
        persistence_observer=owned.append,
        derived_effects_disposition_observer=dispositions.append,
        derived_effects_observer=runners.append
    )
    payload = (persist if entry['kind'] == 'existing' else create).call_args.args[1]
    assert result.processing_deferred is True and result.deferred is False
    assert result.status == ConversationStatus.completed
    assert result.client_processing == (projection if summary_enabled else None)
    assert payload['processing_deferred'] is True
    assert payload['terminal_no_derived_effects'] is True
    assert 'Untrusted local summary' not in str(payload['structured'])
    assert owned == [True] and runners == []
    assert dispositions == [pc.DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS]
    forbidden.assert_not_called()
