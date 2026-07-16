"""Server-authoritative fixture state for the local Chat-first E2E bundle.

This module deliberately does not alter the normal Chat-first routes.  The
harness writes only two fixed local/offline accounts, uses the existing
canonical document builders and intent contracts, and returns no fixture text
or entity data.  Its clock advance makes fixture deferrals due; production
materialization continues to read its normal wall clock.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from config.chat_first_e2e_fixture import (
    CHAT_FIRST_E2E_ENABLED_PRINCIPAL,
    CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL,
    fixture_uid_for_principal,
    is_chat_first_e2e_fixture_uid,
    is_chat_first_e2e_harness_runtime,
)
from database._client import get_firestore_client
import database.action_items as action_items_db
import database.chat_first_intents as intents_db
import database.goals as goals_db
from models.chat_first import (
    ChatFirstSubject,
    ColdStartSequence,
    GoalLinkSpec,
    ProactiveIntent,
    QuestionCardSpec,
    QuestionOption,
    TaskCardSpec,
)
from models.chat_first_e2e import (
    ChatFirstE2EControlEndpointMode,
    ChatFirstE2EExpectedShell,
    ChatFirstE2EFixtureCase,
    ChatFirstE2EFixtureSnapshot,
)
from models.goal import GoalStatus
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

_STATE_COLLECTION = 'chat_first_e2e_harness'
_STATE_DOCUMENT = 'state'
_GOAL_ID = 'chat-first-e2e-goal-v1'
_SECONDARY_GOAL_ID = 'chat-first-e2e-secondary-goal-v1'
_TASK_ID = 'chat-first-e2e-task-v1'
_CAPTURE_ID = 'chat-first-e2e-capture-v1'
_QUESTION_CONTINUITY_KEY = 'chat-first-e2e-question-v1'
_COLD_START_CONTINUITY_KEY = 'cold-start:1'


class ChatFirstE2EFixtureUnavailable(RuntimeError):
    """The fixture route is unavailable outside its local/offline boundary."""


class ChatFirstE2EFixtureIdentityError(RuntimeError):
    """An authenticated account is not one of the isolated fixture users."""


class ChatFirstE2EFixtureNotPrepared(RuntimeError):
    """An advance/snapshot request arrived before a fixture prepare call."""


def _require_harness(uid: str) -> None:
    if not is_chat_first_e2e_harness_runtime():
        raise ChatFirstE2EFixtureUnavailable('chat-first E2E harness is unavailable')
    if not is_chat_first_e2e_fixture_uid(uid):
        raise ChatFirstE2EFixtureIdentityError('chat-first E2E fixture account is required')


def fixture_uid_for_case(fixture_case: ChatFirstE2EFixtureCase) -> str | None:
    """Resolve a case to the only account it may mutate."""

    if fixture_case is ChatFirstE2EFixtureCase.out_of_cohort:
        return fixture_uid_for_principal(CHAT_FIRST_E2E_OUT_OF_COHORT_PRINCIPAL)
    return fixture_uid_for_principal(CHAT_FIRST_E2E_ENABLED_PRINCIPAL)


def _state_ref(uid: str, *, firestore_client: Any):
    return firestore_client.collection('users').document(uid).collection(_STATE_COLLECTION).document(_STATE_DOCUMENT)


def _user_ref(uid: str, *, firestore_client: Any):
    return firestore_client.collection('users').document(uid)


def _entity_refs(uid: str, *, firestore_client: Any) -> dict[str, Any]:
    user_ref = _user_ref(uid, firestore_client=firestore_client)
    question_intent_id = intents_db._stable_id('cfi', uid, 1, 'deferral_reraise', _QUESTION_CONTINUITY_KEY)
    cold_start_intent_id = intents_db._stable_id('cfi', uid, 1, 'cold_start', _COLD_START_CONTINUITY_KEY)
    daily_opener_intent_id = intents_db._stable_id('cfi', uid, 1, 'daily_opener', 'daily:chat-first-e2e')
    question_deferral_id = intents_db._stable_id('cfd', uid, 1, _QUESTION_CONTINUITY_KEY)
    return {
        'control': user_ref.collection('task_intelligence_control').document('state'),
        'goal': user_ref.collection('goals').document(_GOAL_ID),
        'secondary_goal': user_ref.collection('goals').document(_SECONDARY_GOAL_ID),
        'task': user_ref.collection('action_items').document(_TASK_ID),
        'capture': user_ref.collection('conversations').document(_CAPTURE_ID),
        'question_intent': user_ref.collection(intents_db.INTENTS_COLLECTION).document(question_intent_id),
        'cold_start_intent': user_ref.collection(intents_db.INTENTS_COLLECTION).document(cold_start_intent_id),
        'daily_opener_intent': user_ref.collection(intents_db.INTENTS_COLLECTION).document(daily_opener_intent_id),
        'question_deferral': user_ref.collection(intents_db.DEFERRALS_COLLECTION).document(question_deferral_id),
        'budget': user_ref.collection(intents_db.STATE_COLLECTION).document(intents_db.BUDGET_DOCUMENT),
        'state': _state_ref(uid, firestore_client=firestore_client),
    }


def _existing_feature_refs(uid: str, *, firestore_client: Any) -> list[Any]:
    """List only the fixture account's replaceable proactive rows before reset."""

    user_ref = _user_ref(uid, firestore_client=firestore_client)
    refs: list[Any] = []
    for collection_name in (intents_db.INTENTS_COLLECTION, intents_db.DEFERRALS_COLLECTION):
        refs.extend(document.reference for document in user_ref.collection(collection_name).stream())
    return refs


def _unique_document_refs(refs: list[Any]) -> list[Any]:
    """Avoid sending duplicate deletes for deterministic rows in one commit."""

    unique: list[Any] = []
    seen_paths: set[str] = set()
    for ref in refs:
        path = getattr(ref, 'path', None)
        if not isinstance(path, str):
            # Firestore document references expose ``path``.  The fallback
            # keeps the helper usable with minimal hermetic fakes.
            unique.append(ref)
            continue
        if path not in seen_paths:
            seen_paths.add(path)
            unique.append(ref)
    return unique


def _expected_shell(fixture_case: ChatFirstE2EFixtureCase) -> ChatFirstE2EExpectedShell:
    if fixture_case in {
        ChatFirstE2EFixtureCase.enabled,
        ChatFirstE2EFixtureCase.question,
        ChatFirstE2EFixtureCase.cold_start,
    }:
        return ChatFirstE2EExpectedShell.chat_first
    return ChatFirstE2EExpectedShell.legacy


def _control_endpoint_mode(fixture_case: ChatFirstE2EFixtureCase) -> ChatFirstE2EControlEndpointMode:
    if fixture_case is ChatFirstE2EFixtureCase.unreachable_control:
        return ChatFirstE2EControlEndpointMode.unreachable
    return ChatFirstE2EControlEndpointMode.reachable


def _control_for_case(fixture_case: ChatFirstE2EFixtureCase) -> TaskWorkflowControl:
    return TaskWorkflowControl(
        workflow_mode=TaskWorkflowMode.read,
        account_generation=1,
        chat_first_ui_enabled=fixture_case is not ChatFirstE2EFixtureCase.ui_flag_off,
    )


def _goal_payload(*, goal_id: str, title: str, focused: bool, now: datetime) -> dict[str, Any]:
    payload = goals_db._new_goal_payload(
        {
            'goal_id': goal_id,
            'title': title,
            'desired_outcome': 'Validate the Chat-first fixture loop',
            'status': GoalStatus.background.value,
            'source': 'user',
        },
        goal_id=goal_id,
        now=now,
        account_generation=1,
    )
    payload.update(
        {
            'status': GoalStatus.focused.value if focused else GoalStatus.background.value,
            'focus_rank': 0 if focused else None,
            'is_active': True,
        }
    )
    return payload


def _task_payload(*, now: datetime) -> dict[str, Any]:
    return action_items_db._prepare_action_item_for_write(
        {
            'id': _TASK_ID,
            'description': 'E2E fixture task',
            'goal_id': _GOAL_ID,
            'completed': False,
            'owner': 'user',
            # This is deliberately the one task provenance which the cohort
            # archive can resolve. The resulting task-card badge exercises
            # the production fail-closed capture-link policy instead of
            # merely asserting its helper against a synthetic Swift value.
            'source': 'transcription:omi',
            'conversation_id': _CAPTURE_ID,
            'provenance': [],
            'sort_order': 0,
            'indent_level': 0,
            'created_at': now,
            'updated_at': now,
            'account_generation': 1,
        }
    )


def _capture_payload(*, now: datetime) -> dict[str, Any]:
    """The smallest persisted Omi capture shape accepted by the existing archive."""

    return {
        'id': _CAPTURE_ID,
        'source': 'omi',
        'status': 'completed',
        'discarded': False,
        'created_at': now,
        'started_at': now - timedelta(minutes=20),
        'finished_at': now - timedelta(minutes=5),
        'structured': {'title': 'E2E fixture capture'},
        'transcript_segments': [],
        'data_protection_level': 'standard',
    }


def _question() -> QuestionCardSpec:
    return QuestionCardSpec(
        type='questionCard',
        question_id='chat-first-e2e-question-v1',
        text='Which fixture path should continue?',
        subject=ChatFirstSubject(kind='goal', id=_GOAL_ID),
        options=[
            QuestionOption(option_id='continue', label='Continue', prepared_answer='Continue'),
            QuestionOption(option_id='later', label='Ask me later', prepared_answer='Ask me later', defer=True),
        ],
    )


def _question_intent(uid: str, *, now: datetime) -> ProactiveIntent:
    return ProactiveIntent(
        intent_id=intents_db._stable_id('cfi', uid, 1, 'deferral_reraise', _QUESTION_CONTINUITY_KEY),
        continuity_key=_QUESTION_CONTINUITY_KEY,
        account_generation=1,
        source='deferral_reraise',
        subject=ChatFirstSubject(kind='goal', id=_GOAL_ID),
        blocks=[_question()],
        created_at=now,
    )


def _cold_start_intent(uid: str, *, now: datetime) -> ProactiveIntent:
    sequence_id = _COLD_START_CONTINUITY_KEY
    question = QuestionCardSpec(
        type='questionCard',
        question_id='chat-first-e2e-cold-start-question-v1',
        text='What should Omi help with first?',
        subject=ChatFirstSubject(kind='cold_start', id=sequence_id),
        options=[QuestionOption(option_id='start', label='Start', prepared_answer='Start')],
        cold_start_sequence=ColdStartSequence(sequence_id=sequence_id, step=1),
    )
    return ProactiveIntent(
        intent_id=intents_db._stable_id('cfi', uid, 1, 'cold_start', sequence_id),
        continuity_key=sequence_id,
        account_generation=1,
        source='cold_start_sparse',
        subject=question.subject,
        blocks=[question],
        delivery_state='pending_kernel_receipt',
        created_at=now,
    )


def _daily_opener_intent(uid: str, *, now: datetime) -> ProactiveIntent:
    """Build the same deterministic rich opener shape the normal route uses.

    The fixture owns only canonical entities and a server-owned intent; the
    mounted desktop still materializes this row through its ordinary kernel
    receipt path. This gives the cohesive flow a real Goal link and task card
    without inserting a desktop-local card.
    """

    continuity_key = 'daily:chat-first-e2e'
    return ProactiveIntent(
        intent_id=intents_db._stable_id('cfi', uid, 1, 'daily_opener', continuity_key),
        continuity_key=continuity_key,
        account_generation=1,
        source='daily_opener',
        subject=ChatFirstSubject(kind='goal', id=_GOAL_ID),
        blocks=[
            GoalLinkSpec(type='goalLink', goal_id=_GOAL_ID, summary='E2E fixture goal'),
            TaskCardSpec(type='taskCard', task_id=_TASK_ID),
        ],
        created_at=now,
    )


def _completed_rich_cold_start_intent(uid: str, *, now: datetime) -> ProactiveIntent:
    """Record the focused fixture's already-completed first-run exchange.

    The question/deferral flow starts after ordinary first-run materialization
    has finished.  Persisting the same deterministic cold-start row that the
    real path would have delivered prevents an unrelated opener from taking
    the Chat tail, while the question itself still uses the normal server
    materialization and kernel-owned deferral path.
    """

    sequence_id = _COLD_START_CONTINUITY_KEY
    return ProactiveIntent(
        intent_id=intents_db._stable_id('cfi', uid, 1, 'cold_start', sequence_id),
        continuity_key=sequence_id,
        account_generation=1,
        source='cold_start_rich',
        subject=ChatFirstSubject(kind='goal', id=_GOAL_ID),
        blocks=[
            GoalLinkSpec(type='goalLink', goal_id=_GOAL_ID, summary='E2E fixture goal'),
            TaskCardSpec(type='taskCard', task_id=_TASK_ID),
        ],
        delivery_state='delivered',
        created_at=now - timedelta(seconds=1),
        delivered_at=now,
        materialization_receipt_id='chat-first-e2e-completed-cold-start-v1',
    )


def _snapshot_from_rows(
    uid: str,
    *,
    firestore_client: Any,
    prepared_state: dict[str, Any] | None = None,
) -> ChatFirstE2EFixtureSnapshot:
    refs = _entity_refs(uid, firestore_client=firestore_client)
    state = prepared_state if prepared_state is not None else refs['state'].get().to_dict()
    if not isinstance(state, dict):
        raise ChatFirstE2EFixtureNotPrepared('chat-first E2E fixture is not prepared')
    try:
        fixture_case = ChatFirstE2EFixtureCase(state['fixture_case'])
        fixture_revision = int(state['fixture_revision'])
        advanced_seconds = int(state.get('advanced_seconds', 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ChatFirstE2EFixtureNotPrepared('chat-first E2E fixture state is invalid') from exc

    intents = []
    for document in (
        _user_ref(uid, firestore_client=firestore_client).collection(intents_db.INTENTS_COLLECTION).stream()
    ):
        data = document.to_dict()
        if isinstance(data, dict) and data.get('account_generation') == 1:
            intents.append(ProactiveIntent.model_validate(data))
    pending_deferral_count = 0
    for document in (
        _user_ref(uid, firestore_client=firestore_client).collection(intents_db.DEFERRALS_COLLECTION).stream()
    ):
        data = document.to_dict()
        if isinstance(data, dict) and data.get('account_generation') == 1 and data.get('state') == 'pending':
            pending_deferral_count += 1
    return ChatFirstE2EFixtureSnapshot(
        fixture_case=fixture_case,
        fixture_revision=fixture_revision,
        expected_shell=_expected_shell(fixture_case),
        control_endpoint_mode=_control_endpoint_mode(fixture_case),
        advanced_seconds=advanced_seconds,
        materialized_intent_count=sum(intent.delivery_state == 'delivered' for intent in intents),
        ready_intent_count=sum(intent.delivery_state in {'ready', 'pending_kernel_receipt'} for intent in intents),
        proactive_intent_count=len(intents),
        pending_deferral_count=pending_deferral_count,
    )


def prepare_fixture(
    uid: str,
    *,
    fixture_case: ChatFirstE2EFixtureCase,
    firestore_client: Any = None,
) -> ChatFirstE2EFixtureSnapshot:
    """Atomically reset the fixed fixture rows and write one coherent scenario."""

    _require_harness(uid)
    expected_uid = fixture_uid_for_case(fixture_case)
    if expected_uid is None or uid != expected_uid:
        raise ChatFirstE2EFixtureIdentityError('fixture case must use its isolated account')
    client = firestore_client or get_firestore_client()
    refs = _entity_refs(uid, firestore_client=client)
    now = datetime.now(timezone.utc)
    prior_feature_refs = _existing_feature_refs(uid, firestore_client=client)
    # Read the fixture revision before opening its write batch.  This avoids
    # passing an inactive Firestore transaction to DocumentReference.get().
    state_snapshot = refs['state'].get()
    existing_state = state_snapshot.to_dict() if state_snapshot.exists else {}
    revision = int(existing_state.get('fixture_revision', 0)) + 1 if isinstance(existing_state, dict) else 1
    batch = client.batch()

    # All fixture-owned surfaces are deterministic document IDs.  The same
    # batch removes their prior contents before exposing the next case.
    reset_refs = prior_feature_refs + [
        refs[ref_name]
        for ref_name in ('question_intent', 'cold_start_intent', 'daily_opener_intent', 'question_deferral', 'budget')
    ]
    for ref in _unique_document_refs(reset_refs):
        batch.delete(ref)
    batch.set(refs['control'], _control_for_case(fixture_case).persisted_payload())
    batch.set(
        refs['goal'],
        _goal_payload(goal_id=_GOAL_ID, title='E2E fixture goal', focused=True, now=now),
    )
    batch.set(
        refs['secondary_goal'],
        _goal_payload(goal_id=_SECONDARY_GOAL_ID, title='E2E fixture next goal', focused=False, now=now),
    )
    batch.set(refs['task'], _task_payload(now=now))
    batch.set(refs['capture'], _capture_payload(now=now))
    if fixture_case is ChatFirstE2EFixtureCase.cold_start:
        batch.set(refs['cold_start_intent'], _cold_start_intent(uid, now=now).model_dump(mode='python'))
    elif fixture_case is ChatFirstE2EFixtureCase.question:
        batch.set(
            refs['cold_start_intent'],
            _completed_rich_cold_start_intent(uid, now=now).model_dump(mode='python'),
        )
        batch.set(refs['question_intent'], _question_intent(uid, now=now).model_dump(mode='python'))
    elif fixture_case is ChatFirstE2EFixtureCase.enabled:
        batch.set(
            refs['daily_opener_intent'],
            _daily_opener_intent(uid, now=now).model_dump(mode='python'),
        )
    elif fixture_case is ChatFirstE2EFixtureCase.unreachable_control:
        batch.set(refs['question_intent'], _question_intent(uid, now=now).model_dump(mode='python'))
    state = {
        'fixture_case': fixture_case.value,
        'fixture_revision': revision,
        'advanced_seconds': 0,
        'prepared_at': now,
    }
    batch.set(refs['state'], state)
    batch.commit()
    return _snapshot_from_rows(uid, firestore_client=client, prepared_state=state)


def advance_fixture_clock(
    uid: str,
    *,
    seconds: int,
    firestore_client: Any = None,
) -> ChatFirstE2EFixtureSnapshot:
    """Advance fixture deferrals without adding a clock branch to normal Chat.

    The desktop still calls the real materialization endpoint.  This harness
    operation only moves its own pending deferrals to immediately due, so the
    production wall-clock code releases them through the existing store.
    """

    _require_harness(uid)
    client = firestore_client or get_firestore_client()
    refs = _entity_refs(uid, firestore_client=client)
    state_snapshot = refs['state'].get()
    state = state_snapshot.to_dict() if state_snapshot.exists else None
    if not isinstance(state, dict):
        raise ChatFirstE2EFixtureNotPrepared('chat-first E2E fixture is not prepared')
    now = datetime.now(timezone.utc)
    pending_refs = []
    for document in _user_ref(uid, firestore_client=client).collection(intents_db.DEFERRALS_COLLECTION).stream():
        data = document.to_dict()
        if isinstance(data, dict) and data.get('account_generation') == 1 and data.get('state') == 'pending':
            pending_refs.append(document.reference)
    batch = client.batch()
    for ref in pending_refs:
        batch.update(ref, {'due_at': now - timedelta(seconds=1)})
    advanced_state = deepcopy(state)
    advanced_state['advanced_seconds'] = int(advanced_state.get('advanced_seconds', 0)) + seconds
    batch.set(refs['state'], advanced_state)
    batch.commit()
    return _snapshot_from_rows(uid, firestore_client=client, prepared_state=advanced_state)


def snapshot_fixture(uid: str, *, firestore_client: Any = None) -> ChatFirstE2EFixtureSnapshot:
    """Read the harness's bounded outcomes without exposing fixture content."""

    _require_harness(uid)
    client = firestore_client or get_firestore_client()
    return _snapshot_from_rows(uid, firestore_client=client)


def is_control_unreachable(uid: str, *, firestore_client: Any = None) -> bool:
    """Return whether the real control route must simulate a local outage.

    This is intentionally an input to the normal control endpoint only for a
    prepared fixture account in a local/offline process.  It is not a derived
    capability and it cannot be reached in any deployable server route table.
    """

    if not is_chat_first_e2e_fixture_uid(uid):
        return False
    client = firestore_client or get_firestore_client()
    snapshot = _state_ref(uid, firestore_client=client).get()
    state = snapshot.to_dict() if snapshot.exists else None
    return isinstance(state, dict) and state.get('fixture_case') == ChatFirstE2EFixtureCase.unreachable_control.value


__all__ = [
    'ChatFirstE2EFixtureIdentityError',
    'ChatFirstE2EFixtureNotPrepared',
    'ChatFirstE2EFixtureUnavailable',
    'advance_fixture_clock',
    'fixture_uid_for_case',
    'is_control_unreachable',
    'prepare_fixture',
    'snapshot_fixture',
]
