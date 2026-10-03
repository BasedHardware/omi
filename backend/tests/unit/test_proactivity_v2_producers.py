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
from routers import commitment_followup as worker
from utils import commitment_followup_tasks as scheduler


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

    chat_write = MagicMock()
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
@pytest.mark.parametrize('pipeline', ['legacy', 'v2', 'typo'])
async def test_exclusive_dispatch(lane, pipeline):
    lane.monkeypatch.setenv('MENTOR_PIPELINE', pipeline)
    lane.monkeypatch.setattr(integration, 'is_trial_paywalled', lambda *args: False)
    lane.monkeypatch.setattr(integration, 'process_mentor_notification', lambda *args: [{'text': 'test'}])
    old = MagicMock(return_value=None)
    new = AsyncMock(return_value=None)
    lane.monkeypatch.setattr(integration, '_process_mentor_proactive_notification', old)
    lane.monkeypatch.setattr(producers, 'evaluate_mentor_event', new)
    lane.monkeypatch.setattr(integration, 'get_available_apps', lambda *args: [])
    await integration._async_trigger_realtime_integrations('u', [], 'c')
    assert old.call_count == int(pipeline == 'legacy')
    assert new.await_count == int(pipeline == 'v2')


@pytest.mark.asyncio
async def test_v2_failure_never_invokes_legacy(lane):
    lane.monkeypatch.setenv('MENTOR_PIPELINE', 'v2')
    lane.monkeypatch.setattr(integration, 'is_trial_paywalled', lambda *args: False)
    lane.monkeypatch.setattr(integration, 'process_mentor_notification', lambda *args: [{'text': 'test'}])
    old = MagicMock(return_value=None)
    lane.monkeypatch.setattr(integration, '_process_mentor_proactive_notification', old)
    lane.monkeypatch.setattr(producers.spine, 'ensure_admitted', AsyncMock(side_effect=ProactivityDenied('not_paid')))
    lane.monkeypatch.setattr(integration, 'get_available_apps', lambda *args: [])
    await integration._async_trigger_realtime_integrations('u', [], 'c')
    old.assert_not_called()
    lane.model.assert_not_awaited()


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
