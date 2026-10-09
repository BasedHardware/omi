"""Hermetic producer decisions and actual dispatch/outcome wiring."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from config.mentor_v2 import MentorV2Config, mentor_config
from config.proactivity_v2 import ProactivityDenied
from utils import proactivity_producers as producers
from utils import app_integrations as integration
from utils import proactivity_flags as flags
from routers import commitment_followup as worker
from utils import commitment_followup_tasks as scheduler
from tests.unit.test_proactivity_v2_budget import store


def test_mentor_context_preserves_past_conversation_items_and_excludes_locked(monkeypatch):
    newest = {'id': 'newest', 'text': 'Newer context'}
    older = {'id': 'older', 'text': 'Older context'}
    monkeypatch.setattr(integration, 'get_prompt_memories', lambda uid: ('User', '- Known fact'))
    monkeypatch.setattr(integration, 'get_user_goals', lambda *args, **kwargs: [])
    monkeypatch.setattr(integration, 'get_app_messages', lambda *args, **kwargs: [])
    monkeypatch.setattr(integration, 'current_date_for_uid', lambda uid: '2026-10-05')
    monkeypatch.setattr(integration, 'get_user_language_preference', lambda uid: 'en')
    monkeypatch.setattr(
        integration.conversations_db,
        'get_conversations',
        lambda *args, **kwargs: [newest, {'id': 'locked', 'is_locked': True}, older],
    )
    monkeypatch.setattr(integration, 'deserialize_conversations', lambda rows: rows)
    calls = []

    def render(rows):
        calls.append(rows)
        return 'Conversation #1\n' + rows[0]['text']

    monkeypatch.setattr(integration, 'conversations_to_string', render)
    context = producers.mentor_context('u', 3, 0.78)
    assert calls == [[newest], [older]]
    assert context['past_conversations'] == ['Conversation #1\nNewer context', 'Conversation #2\nOlder context']


@pytest.fixture
def lane(monkeypatch):
    item = {
        'uid': 'u',
        'producer': 'conversation_mentor_v2',
        'item_id': 'a' * 32,
        'source_kind': 'conversation',
        'source_id': 'c',
    }
    claim = AsyncMock(return_value=item)
    model = AsyncMock()
    publish, push, close = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(producers.spine, 'claim_item', claim)
    monkeypatch.setattr(producers.spine, 'run_proactivity_model', model)
    monkeypatch.setattr(producers.spine, 'publish_item', publish)
    monkeypatch.setattr(producers.spine, 'push_item', push)
    monkeypatch.setattr(producers.spine, 'close_item', close)
    score_write = AsyncMock()
    monkeypatch.setattr(producers.spine, 'record_usefulness_score', score_write)
    history_fn = producers.mentor_delivery_history
    monkeypatch.setattr(producers, 'mentor_delivery_history', lambda uid: ['Earlier advice'])
    import database.chat as chat

    chat_write = MagicMock(return_value=SimpleNamespace(id='chat-message'))
    monkeypatch.setattr(producers.spine, 'record_mentor_chat', AsyncMock())
    monkeypatch.setattr(chat, 'add_app_message', chat_write)
    config, prompts = mentor_config()
    monkeypatch.setattr(producers, 'mentor_config', lambda: (config, prompts))

    async def respond(*, item, step, request):
        outputs = {
            'gate': {'is_relevant': True, 'relevance_score': 0.99, 'reasoning': 'detail', 'context_summary': 'context'},
            'generate': {
                'notification_text': 'Call Alex about the Friday deadline',
                'reasoning': 'Friday',
                'confidence': 0.99,
                'category': 'productivity',
            },
            'critic': {'approved': True, 'reasoning': 'useful', 'safety_escalation': False},
            'phrase': {'title': 'Call Alex', 'body': 'Your saved task to call Alex is due.'},
        }
        if step == 'dedupe':
            return {'answers': {'repeat': {'score': 0}}}
        if step == 'prefilter':
            return {'answers': {'nothing_worth_saying': {'noul': 0.1}}}
        if step == 'usefulness':
            return {'answers': {'useful': {'noul': 0.8}}}
        return {'choices': [{'message': {'content': json.dumps(outputs[step])}}]}

    model.side_effect = respond
    context = dict(
        user_name='User',
        user_facts='',
        goals=[],
        recent_notifications=[],
        current_date='2026-10-03',
        past_conversations='None',
        frequency_guidance='Useful',
        output_language='en',
        base_threshold=0.78,
    )
    return SimpleNamespace(
        item=item,
        claim=claim,
        model=model,
        publish=publish,
        push=push,
        close=close,
        score_write=score_write,
        config=config,
        prompts=prompts,
        context=context,
        chat_write=chat_write,
        respond=respond,
        monkeypatch=monkeypatch,
        history_fn=history_fn,
    )


async def mentor(lane):
    return await producers.produce_mentor(
        'u', 'c', [{'text': 'Call Alex', 'is_user': True, 'timestamp': 1}], lane.context
    )


@pytest.mark.asyncio
async def test_default_prefilter_disabled_mentor_publishes_push_and_thread(lane):
    assert await mentor(lane)
    assert [call.kwargs['step'] for call in lane.model.call_args_list] == [
        'gate',
        'generate',
        'critic',
        'usefulness',
        'dedupe',
    ]
    lane.score_write.assert_awaited_once_with(item=lane.item, score=0.8)
    lane.publish.assert_awaited_once()
    lane.push.assert_awaited_once()
    lane.chat_write.assert_called_once()
    assert lane.chat_write.call_args.kwargs['proactivity_item_id'] == lane.item['item_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('p_nothing,expected', [(0.1, True), (0.9, False)])
async def test_prefilter_enabled_correct_probability_orientation(lane, p_nothing, expected):
    lane.monkeypatch.setattr(
        producers, 'mentor_config', lambda: (lane.config.model_copy(update={'prefilter_threshold': 0.5}), lane.prompts)
    )

    async def response(**kwargs):
        if kwargs['step'] == 'prefilter':
            return {'answers': {'nothing_worth_saying': {'noul': p_nothing}}}
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert bool(await mentor(lane)) == expected
    assert lane.publish.await_count == int(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['prefilter', 'dedupe', 'usefulness'])
async def test_jev_failure_proceeds_without_retry(lane, step):
    lane.monkeypatch.setattr(
        producers, 'mentor_config', lambda: (lane.config.model_copy(update={'prefilter_threshold': 0.5}), lane.prompts)
    )

    async def response(**kwargs):
        if kwargs['step'] == step:
            raise RuntimeError('provider error')
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert await mentor(lane)
    assert sum(c.kwargs['step'] == step for c in lane.model.call_args_list) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('score,suppressed', [(2.1, True), (2.099, False)])
async def test_dedupe_threshold_inclusive(lane, score, suppressed):
    async def response(**kwargs):
        if kwargs['step'] == 'dedupe':
            return {'answers': {'repeat': {'score': score}}}
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert bool(await mentor(lane)) == (not suppressed)
    if suppressed:
        lane.close.assert_awaited_once_with(item=lane.item, state='suppressed', reason='duplicate')
        lane.push.assert_not_awaited()
        lane.chat_write.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('guard,delivered', [('suppress', False), ('allow', True)])
async def test_safety_structured_output_guard(lane, guard, delivered):
    lane.monkeypatch.setattr(
        producers, 'mentor_config', lambda: (lane.config.model_copy(update={'safety_escalation': guard}), lane.prompts)
    )

    async def response(**kwargs):
        if kwargs['step'] == 'critic':
            return {
                'choices': [
                    {
                        'message': {
                            'content': json.dumps({'approved': True, 'reasoning': 'urgent', 'safety_escalation': True})
                        }
                    }
                ]
            }
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert bool(await mentor(lane)) == delivered
    if not delivered:
        lane.close.assert_awaited_once_with(item=lane.item, state='suppressed', reason='safety_escalation')


@pytest.mark.asyncio
async def test_claim_denial_free_user_makes_zero_model_calls(lane):
    lane.claim.side_effect = ProactivityDenied('not_paid')
    assert await mentor(lane) is None
    lane.model.assert_not_awaited()
    lane.publish.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['gate', 'generate', 'critic', 'dedupe', 'usefulness'])
async def test_budget_denial_stops_pipeline(lane, step):
    async def response(**kwargs):
        if kwargs['step'] == step:
            raise ProactivityDenied('budget_exhausted')
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert await mentor(lane) is None
    lane.publish.assert_not_awaited()
    lane.push.assert_not_awaited()


@pytest.mark.asyncio
async def test_push_denied_retains_feed_and_thread(lane):
    lane.push.side_effect = ProactivityDenied('quiet_hours')
    assert await mentor(lane)
    lane.publish.assert_awaited_once()
    lane.chat_write.assert_called_once()


@pytest.mark.asyncio
async def test_followup_one_call_feed_only_idempotent_no_task_mutation(lane):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = {'conversation_id': 'c', 'description': 'Call Alex', 'due_at': due, 'completed': False}
    read = MagicMock(return_value=task)
    lane.monkeypatch.setattr(producers.tasks, 'get_action_item', read)
    mutations = [MagicMock(), MagicMock()]
    lane.monkeypatch.setattr(producers.tasks, 'update_action_item', mutations[0])
    lane.monkeypatch.setattr(producers.tasks, 'mark_action_item_completed', mutations[1])
    lane.claim.side_effect = [lane.item, ProactivityDenied('duplicate')]
    await producers.produce_followup('u', 't', due.isoformat())
    await producers.produce_followup('u', 't', due.isoformat())
    assert lane.model.await_count == lane.publish.await_count == 1
    lane.push.assert_not_awaited()
    for mutation in mutations:
        mutation.assert_not_called()
    assert task['completed'] is False
    assert lane.claim.call_args.kwargs['source']['source_event_id'] == 'due'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change',
    [
        {'completed': True},
        {'conversation_id': None},
        {'status': 'cancelled'},
        {'due_at': datetime.now(timezone.utc) + timedelta(days=1)},
        {'is_locked': True},
    ],
)
async def test_followup_ineligible_task_no_claim(lane, change):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = dict(conversation_id='c', due_at=due, completed=False, **{})
    task.update(change)
    lane.monkeypatch.setattr(producers.tasks, 'get_action_item', MagicMock(return_value=task))
    await producers.produce_followup('u', 't', due.isoformat())
    lane.claim.assert_not_awaited()


def test_prompts_legacy_1_bytes_and_config_validation():
    config, prompts = mentor_config()
    assert config.prefilter_threshold is None
    assert config.usefulness_judge == 'shadow'
    assert config.usefulness_threshold == 0.5
    assert prompts == dict(
        gate=producers.legacy.GATE_PROMPT,
        generate=producers.legacy.GENERATE_PROMPT,
        critic=producers.legacy.CRITIC_PROMPT,
    )
    with pytest.raises(ValueError):
        MentorV2Config(safety_escalation='typo')
    for invalid in [{'usefulness_judge': 'typo'}, {'usefulness_threshold': -0.1}, {'usefulness_threshold': 1.1}]:
        with pytest.raises(ValueError):
            MentorV2Config(**invalid)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'pipeline,flag,expected',
    [
        # legacy/v2 host-wide modes were deleted with the legacy pipeline: any
        # non-cohort value (including a stale flip) invokes no mentor path.
        ('legacy', True, 'none'),
        ('v2', True, 'none'),
        ('typo', True, 'none'),
        ('cohort', True, 'v2'),
        ('cohort', False, 'none'),
        ('cohort', None, 'none'),
        ('cohort', 'error', 'none'),
    ],
)
async def test_exclusive_dispatch(lane, pipeline, flag, expected):
    lane.monkeypatch.setenv('MENTOR_PIPELINE', pipeline)

    def resolve(uid):
        if flag == 'error':
            raise flags.ProactivityFlagUnavailable('APIError', 429)
        return flag is True

    flag_lookup = MagicMock(side_effect=resolve)
    lane.monkeypatch.setattr(integration.proactivity_flags, 'enabled', flag_lookup)
    lane.monkeypatch.setattr(integration, 'is_trial_paywalled', lambda *args: False)
    admission = MagicMock(return_value=[{'text': 'test'}])
    lane.monkeypatch.setattr(integration, 'process_mentor_notification', admission)
    new = AsyncMock(return_value=None)
    lane.monkeypatch.setattr(producers, 'evaluate_mentor_event', new)
    lane.monkeypatch.setattr(integration, 'get_available_apps', lambda *args: [])
    await integration._async_trigger_realtime_integrations('u', [], 'c')
    assert new.await_count == int(expected == 'v2')
    assert admission.call_count == int(pipeline == 'cohort')
    assert flag_lookup.call_count == int(pipeline == 'cohort')
    if pipeline == 'cohort':
        admission.assert_called_once_with('u', [])
    if expected == 'v2':
        new.assert_awaited_once_with('u', 'c', admission.return_value)


@pytest.mark.asyncio
@pytest.mark.parametrize('messages', [None, [], [{'text': 'test'}]])
async def test_cohort_resolves_only_after_shared_admission(lane, messages):
    lane.monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    lane.monkeypatch.setattr(integration, 'is_trial_paywalled', lambda *args: False)
    calls = []

    def admit(uid, segments):
        calls.append('admit')
        return messages

    def resolve(uid):
        calls.append('flag')
        return True

    lane.monkeypatch.setattr(integration, 'process_mentor_notification', admit)
    lane.monkeypatch.setattr(integration.proactivity_flags, 'enabled', resolve)
    new = AsyncMock()
    lane.monkeypatch.setattr(producers, 'evaluate_mentor_event', new)
    lane.monkeypatch.setattr(integration, 'get_available_apps', lambda *args: [])
    await integration._async_trigger_realtime_integrations('u', [], 'c')
    assert calls == (['admit', 'flag'] if messages else ['admit'])
    assert new.await_count == int(bool(messages))


@pytest.mark.asyncio
async def test_invalid_flip_during_shared_admission_invokes_neither_lane(lane):
    lane.monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    lane.monkeypatch.setattr(integration, 'is_trial_paywalled', lambda *args: False)

    def admit(uid, segments):
        lane.monkeypatch.setenv('MENTOR_PIPELINE', 'typo')
        return [{'text': 'test'}]

    flag_lookup = MagicMock(side_effect=AssertionError('invalid flip must not resolve flags'))
    lane.monkeypatch.setattr(integration, 'process_mentor_notification', admit)
    lane.monkeypatch.setattr(integration.proactivity_flags, 'enabled', flag_lookup)
    new = AsyncMock()
    lane.monkeypatch.setattr(producers, 'evaluate_mentor_event', new)
    lane.monkeypatch.setattr(integration, 'get_available_apps', lambda *args: [])
    await integration._async_trigger_realtime_integrations('u', [], 'c')
    flag_lookup.assert_not_called()
    new.assert_not_awaited()


@pytest.mark.asyncio
async def test_flag_denial_does_not_abort_app_integrations(lane):
    """A cohort flag error denies the mentor lane only; app lookup still runs."""
    lane.monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    lane.monkeypatch.setattr(integration, 'is_trial_paywalled', lambda *args: False)
    lane.monkeypatch.setattr(integration, 'process_mentor_notification', lambda *args: [{'text': 'test'}])
    lane.monkeypatch.setattr(
        integration.proactivity_flags,
        'mentor_pipeline',
        MagicMock(side_effect=ProactivityDenied('flag_unavailable')),
    )
    new = AsyncMock()
    lane.monkeypatch.setattr(producers, 'evaluate_mentor_event', new)
    apps = MagicMock(return_value=[])
    lane.monkeypatch.setattr(integration, 'get_available_apps', apps)
    assert await integration._async_trigger_realtime_integrations('u', [], 'c') == {}
    apps.assert_called_once_with('u')
    new.assert_not_awaited()


@pytest.mark.asyncio
async def test_mentor_failure_logs_only_metadata(lane, caplog):
    """The v2 failure log line carries metadata only, never provider content."""
    secret = 'PRIVATE_TRANSCRIPT_NEVER_STORED_5921'

    async def fail(**kwargs):
        raise RuntimeError(secret)

    lane.model.side_effect = fail
    with caplog.at_level('INFO'):
        assert await mentor(lane) is None
    assert 'mentor_v2 evaluation_failed' in caplog.text
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_followup_free_user_zero_calls(lane):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    lane.monkeypatch.setattr(
        producers.tasks,
        'get_action_item',
        MagicMock(return_value={'conversation_id': 'c', 'due_at': due, 'completed': False}),
    )
    lane.claim.side_effect = ProactivityDenied('not_paid')
    await producers.produce_followup('u', 't', due.isoformat())
    lane.model.assert_not_awaited()
    lane.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_followup_completed_during_generation_suppressed(lane):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = {'conversation_id': 'c', 'due_at': due, 'completed': False}
    lane.monkeypatch.setattr(
        producers.tasks, 'get_action_item', MagicMock(side_effect=[task, dict(task, completed=True)])
    )
    await producers.produce_followup('u', 't', due.isoformat())
    lane.publish.assert_not_awaited()
    lane.close.assert_awaited_once_with(item=lane.item, state='suppressed', reason='source_changed')


def test_dedupe_history_last_five_delivered_excludes_human_and_unexposed(lane):
    from database import proactivity_producers as storage
    import database.chat as chat

    now = datetime.now(timezone.utc)
    lane.monkeypatch.setattr(
        storage, 'delivered_mentor_items', lambda uid: [{'delivered_at': now, 'body': 'v2 delivered'}]
    )
    lane.monkeypatch.setattr(producers.spine, 'decode_feed_item', lambda uid, item: SimpleNamespace(body=item['body']))
    lane.monkeypatch.setattr(
        chat,
        'get_app_messages',
        lambda *args, **kwargs: [
            {'sender': 'human', 'text': 'reply', 'created_at': now},
            {'sender': 'ai', 'text': 'unexposed', 'proactivity_item_id': 'x', 'created_at': now},
            *[{'sender': 'ai', 'text': str(i), 'created_at': now - timedelta(minutes=i + 1)} for i in range(6)],
        ],
    )
    assert lane.history_fn('u') == ['v2 delivered', '0', '1', '2', '3']


def test_due_scheduler_named_dedup_and_opaque_payload(monkeypatch):
    enqueue = MagicMock()
    monkeypatch.setattr(scheduler.cloud_tasks, 'enqueue_named_task', enqueue)
    monkeypatch.setattr(scheduler, 'enabled', lambda uid: True)
    for suffix, value in [
        ('QUEUE', 'queue'),
        ('HANDLER_URL', 'https://example.invalid/run'),
        ('INVOKER_SA', 'worker@example.invalid'),
    ]:
        monkeypatch.setenv('COMMITMENT_FOLLOWUP_TASKS_' + suffix, value)
    due = datetime.now(timezone.utc) + timedelta(days=60)
    scheduler.schedule_followup('u', 't', due)
    scheduler.schedule_followup('u', 't', due)
    assert enqueue.call_count == 2
    first, second = enqueue.call_args_list
    assert first.args[2] == second.args[2]
    assert first.args[3] == {'uid': 'u', 'task_id': 't', 'due_revision': due.isoformat()}
    assert 0 < first.kwargs['schedule_at'] - datetime.now(timezone.utc).timestamp() < timedelta(days=29).total_seconds()


@pytest.mark.asyncio
async def test_due_worker_replay_uses_same_identity_and_no_client_auth(monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr(worker, 'produce_followup', run)
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    request = SimpleNamespace(
        json=AsyncMock(return_value={'uid': 'u', 'task_id': 't', 'due_revision': due.isoformat()})
    )
    assert await worker.run_commitment_followup(request, 0) == {'status': 'acked'}
    assert await worker.run_commitment_followup(request, 1) == {'status': 'acked'}
    assert run.call_args_list[0] == run.call_args_list[1]


def test_due_worker_oidc_is_required_when_config_absent(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.delenv('COMMITMENT_FOLLOWUP_TASKS_HANDLER_URL', raising=False)
    monkeypatch.delenv('COMMITMENT_FOLLOWUP_TASKS_INVOKER_SA', raising=False)
    with pytest.raises(HTTPException) as exc:
        scheduler.verify_followup_task(SimpleNamespace(headers={}))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize('step', ['dedupe', 'usefulness'])
async def test_gateway_jev_routing_and_typed_budget_denial(monkeypatch, step):
    import httpx
    from utils.llm import gateway_client as gateway

    monkeypatch.setattr(gateway, 'llm_gateway_headers', lambda **kwargs: {})
    monkeypatch.setattr(gateway, 'get_llm_gateway_base_url', lambda: 'https://gateway.invalid')
    request = httpx.Request('POST', 'https://gateway.invalid/v1/systemone')
    client = SimpleNamespace(
        post=AsyncMock(
            return_value=httpx.Response(
                400,
                request=request,
                json={
                    'error': {'param': 'proactivity_admission', 'message': 'proactivity admission denied: call_limit'}
                },
            )
        )
    )
    monkeypatch.setattr(gateway, 'get_llm_gateway_client', lambda: client)
    with pytest.raises(ProactivityDenied, match='gateway_admission_denied'):
        await gateway.run_proactivity_gateway(
            uid='u',
            item_id='a' * 32,
            producer='conversation_mentor_v2',
            call_id='call',
            step=step,
            request={'state': 'data', 'questions': {}},
        )
    assert client.post.call_args.args[0].endswith('/v1/systemone')
    assert client.post.call_args.kwargs['json']['model'] == 'omi:auto:jev-decisions'


@pytest.mark.asyncio
async def test_publication_due_race_closed_suppressed(lane):
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    lane.monkeypatch.setattr(
        producers.tasks,
        'get_action_item',
        MagicMock(return_value={'conversation_id': 'c', 'due_at': due, 'completed': False}),
    )
    lane.publish.side_effect = ProactivityDenied('source_changed')
    await producers.produce_followup('u', 't', due.isoformat())
    lane.close.assert_awaited_once_with(item=lane.item, state='suppressed', reason='source_changed')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'mode,score,delivered',
    [('off', 0.1, True), ('shadow', 0.1, True), ('enforce', 0.499, False), ('enforce', 0.5, True)],
)
async def test_usefulness_modes_and_threshold_boundary(lane, mode, score, delivered):
    lane.monkeypatch.setattr(
        producers, 'mentor_config', lambda: (lane.config.model_copy(update={'usefulness_judge': mode}), lane.prompts)
    )

    async def response(**kwargs):
        if kwargs['step'] == 'usefulness':
            return {'answers': {'useful': {'noul': score}}}
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert bool(await mentor(lane)) == delivered
    assert lane.publish.await_count == lane.push.await_count == lane.chat_write.call_count == int(delivered)
    if mode == 'off':
        lane.score_write.assert_not_awaited()
        assert all(c.kwargs['step'] != 'usefulness' for c in lane.model.call_args_list)
    else:
        lane.score_write.assert_awaited_once_with(item=lane.item, score=score)
    if not delivered:
        lane.close.assert_awaited_once_with(item=lane.item, state='suppressed', reason='usefulness_judge')
        assert all(c.kwargs['step'] != 'dedupe' for c in lane.model.call_args_list)


@pytest.mark.asyncio
async def test_usefulness_request_has_goals_draft_and_last_eight_speaker_lines(lane):
    created_at = datetime(2026, 10, 3, tzinfo=timezone.utc)
    lane.context['goals'] = [{'title': 'Ship the project', 'created_at': created_at}]
    messages = [{'text': f'line {i}', 'is_user': i % 2 == 0, 'timestamp': i} for i in range(12)]
    assert await producers.produce_mentor('u', 'c', messages, lane.context)
    call = next(c for c in lane.model.call_args_list if c.kwargs['step'] == 'usefulness')
    state = json.loads(call.kwargs['request']['state'])
    assert state == {
        'user_name': 'User',
        'user_goals': [{'title': 'Ship the project', 'created_at': created_at.isoformat()}],
        'proposed_notification': 'Call Alex about the Friday deadline',
        'recent_conversation': [('USER: ' if i % 2 == 0 else 'OTHER: ') + f'line {i}' for i in range(4, 12)],
    }
    assert call.kwargs['request']['questions'] == {'useful': producers.USEFULNESS_QUESTION}
    assert lane.context['goals'] == [{'title': 'Ship the project', 'created_at': created_at}]


@pytest.mark.asyncio
@pytest.mark.parametrize('approved,safety', [(False, False), (True, True)])
async def test_shadow_scores_before_existing_critic_suppression(lane, approved, safety):
    async def response(**kwargs):
        if kwargs['step'] == 'critic':
            return {
                'choices': [
                    {
                        'message': {
                            'content': json.dumps(
                                {'approved': approved, 'reasoning': 'decision', 'safety_escalation': safety}
                            )
                        }
                    }
                ]
            }
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert await mentor(lane) is None
    lane.score_write.assert_awaited_once_with(item=lane.item, score=0.8)
    lane.publish.assert_not_awaited()
    assert lane.close.call_args.kwargs['reason'] == ('safety_escalation' if safety else 'model_silent')


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_score', [True, -0.1, 1.1, float('nan'), float('inf')])
async def test_usefulness_bad_probability_fails_open_in_enforce(lane, bad_score):
    lane.monkeypatch.setattr(
        producers,
        'mentor_config',
        lambda: (lane.config.model_copy(update={'usefulness_judge': 'enforce'}), lane.prompts),
    )

    async def response(**kwargs):
        if kwargs['step'] == 'usefulness':
            return {'answers': {'useful': {'noul': bad_score}}}
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert await mentor(lane)
    lane.score_write.assert_not_awaited()
    lane.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_usefulness_score_storage_failure_denies_unmeasured_delivery(lane):
    lane.score_write.side_effect = ConnectionError('offline')
    assert await mentor(lane) is None
    lane.publish.assert_not_awaited()
    lane.close.assert_awaited_once_with(item=lane.item, state='failed', reason='generation_failed')


@pytest.mark.asyncio
async def test_usefulness_provider_error_fails_open_in_enforce(lane):
    lane.monkeypatch.setattr(
        producers,
        'mentor_config',
        lambda: (lane.config.model_copy(update={'usefulness_judge': 'enforce'}), lane.prompts),
    )

    async def response(**kwargs):
        if kwargs['step'] == 'usefulness':
            raise RuntimeError('Jev unavailable')
        return await lane.respond(**kwargs)

    lane.model.side_effect = response
    assert await mentor(lane)
    lane.score_write.assert_not_awaited()
    lane.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_success_chat_failure_reply_cannot_fabricate_delivery(lane, store):
    from database import proactivity as ledger
    from database import proactivity_producers as mapping
    from tests.unit.test_proactivity_v2_budget import NOW
    from tests.unit.test_proactivity_v2_ledger import ready
    from tests.unit.test_proactivity_v2_producer_outcomes import query_for

    item = ready(store, producer='conversation_mentor_v2')
    lane.claim.return_value = dict(item, uid='u')
    lane.chat_write.side_effect = ConnectionError('chat write failed')

    async def chat_result(*, item, status, message_id=''):
        ledger.record_mentor_chat(
            uid='u',
            item_id=item['item_id'],
            claim_token=item['claim_token'],
            status=status,
            message_id=message_id,
            firestore_client=store,
            now=NOW,
        )

    lane.monkeypatch.setattr(producers.spine, 'record_mentor_chat', chat_result)
    assert await mentor(lane) is None
    lane.push.assert_not_awaited()
    lane.close.assert_not_awaited()
    lane.monkeypatch.setattr(mapping, 'utc_now', lambda: NOW + timedelta(minutes=2))
    lane.monkeypatch.setattr(mapping, 'recent_mentor_query', lambda *args: query_for(store, item))
    mapping.record_mentor_reply('u', firestore_client=store)
    row = store.rows[('users', 'u', ledger.ITEMS, item['item_id'])]
    assert row['state'] == 'ready' and row['mentor_chat_state'] == 'failed'
    assert not row['delivered'] and not row['acted_24h'] and 'replied' not in row['outcomes']


@pytest.mark.parametrize('fault', ['preclaim', 'claimed_unsent', 'ambiguous_attempt'])
def test_followup_http_recovery_without_duplicate_spend(store, monkeypatch, fault):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from database import proactivity as ledger
    from tests.unit.test_proactivity_v2_budget import NOW, Redis
    from llm_gateway.gateway import proactivity_budget as gate
    from llm_gateway.gateway.accounting import AttemptTrace
    from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
    from llm_gateway.gateway.resolver import resolve_chat_completion_route
    from llm_gateway.gateway.config_loader import load_gateway_config
    from llm_gateway.gateway.credentials import build_omi_managed_credential_context
    from llm_gateway.gateway.auth import ServiceCaller
    from tests.unit.test_proactivity_v2_gateway import Provider, context
    from database.proactivity_budget import BudgetAuthority
    from database import proactivity_budget as money

    clock = [NOW]
    due = NOW - timedelta(minutes=1)
    task = {'conversation_id': 'c', 'due_at': due, 'completed': False, 'description': 'synthetic'}
    store.rows[('users', 'u', 'action_items', 'a')] = task
    monkeypatch.setattr(producers.tasks, 'get_action_item', lambda *args: task)
    real_claim = ledger.claim_item
    claims = []

    async def claim_item(**kwargs):
        claims.append(1)
        if fault == 'preclaim' and len(claims) == 1:
            raise ConnectionError('transient before claim')
        source = kwargs['source']
        return dict(
            real_claim(uid='u', producer='commitment_followup', **source, firestore_client=store, now=clock[0]), uid='u'
        )

    monkeypatch.setattr(producers.spine, 'claim_item', claim_item)

    async def admit(*args):
        pass

    monkeypatch.setattr(producers.spine, 'ensure_admitted', admit)
    monkeypatch.setenv('LLM_GATEWAY_ACCOUNTING_ENABLED', 'true')
    monkeypatch.setattr(
        money,
        'BudgetAuthority',
        lambda: BudgetAuthority(firestore_client=store, redis_client=Redis(), clock=lambda: clock[0]),
    )
    provider = Provider(fail=fault == 'ambiguous_attempt')
    model_calls = []
    monkeypatch.setattr(
        producers.spine, 'close_item', AsyncMock(side_effect=ConnectionError('terminal write unavailable'))
    )

    async def model(**kwargs):
        model_calls.append(1)
        if fault == 'claimed_unsent' and len(model_calls) == 1:
            raise ConnectionError('pre-dispatch infrastructure failure')
        route = resolve_chat_completion_route(
            load_gateway_config(), dict(kwargs['request'], model='omi:auto:proactive-notification')
        )
        with gate.attempt_scope(context(kwargs['item'])):
            await execute_chat_completion(
                route,
                build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='u')),
                ProviderRegistry({'openai': provider}),
                attempt_trace=AttemptTrace(),
            )
        return {'choices': [{'message': {'content': json.dumps({'title': 'Due', 'body': 'Task due'})}}]}

    monkeypatch.setattr(producers.spine, 'run_proactivity_model', model)

    async def publish(**kwargs):
        item = kwargs['item']
        ledger.publish_item(
            uid='u',
            item_id=item['item_id'],
            claim_token=item['claim_token'],
            encrypted_content='synthetic',
            source_guard=kwargs['source_guard'],
            firestore_client=store,
            now=NOW,
        )

    monkeypatch.setattr(producers.spine, 'publish_item', publish)
    app = FastAPI()
    app.include_router(worker.router)
    app.dependency_overrides[worker.verify_followup_task] = lambda: 0
    payload = dict(uid='u', task_id='a', due_revision=due.isoformat())
    with TestClient(app) as client:
        assert client.post('/v1/commitment-followup-jobs/run', json=payload).status_code == 503
        assert provider.calls == int(fault == 'ambiguous_attempt')
        if fault != 'preclaim':
            assert client.post('/v1/commitment-followup-jobs/run', json=payload).status_code == 503
            clock[0] = NOW + timedelta(minutes=6)
            for name in ['conversation_mentor_v2', 'commitment_followup']:
                store.rows[(ledger.CONTROLS, name)]['checked_at'] = clock[0]
        assert client.post('/v1/commitment-followup-jobs/run', json=payload).status_code == 200
        assert client.post('/v1/commitment-followup-jobs/run', json=payload).status_code == 200
    assert provider.calls == 1
    row = next(v for k, v in store.rows.items() if k[:3] == ('users', 'u', ledger.ITEMS))
    assert len(row['attempts']) == 1
    if fault == 'ambiguous_attempt':
        assert row['state'] == 'failed' and row['cost_status'] == 'indeterminate'
        assert row['charged_micro_usd'] == row['reserved_micro_usd'] > 0
    else:
        assert row['state'] == 'ready'


def test_v2_listen_wakeup_uses_isolated_redis(monkeypatch):
    from unittest.mock import Mock
    from database import proactivity_redis

    client = Mock()
    monkeypatch.setattr(proactivity_redis, 'get_client', lambda: client)
    producers.spine._publish_listen_wakeup('synthetic', {'notification_type': 'proactivity_v2'})
    assert client.publish.call_args.args[0] == producers.spine.redis_db.PROACTIVE_MESSAGE_CHANNEL
    assert json.loads(client.publish.call_args.args[1]) == {
        'uid': 'synthetic',
        'notification_type': 'proactivity_v2',
    }
