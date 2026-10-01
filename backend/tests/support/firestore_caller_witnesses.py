"""Named runtime witnesses for the ``database.conversations`` call surface.

Replaces the retired fingerprint snapshot: every statically discovered
``get_conversations*`` call-site binding maps to named ``CallerProfile`` rows
here, and each witness recipe executes the *real* owning function while the
query helper is monkeypatched to capture ``inspect.signature``-bound
arguments. AST discovery stays the detection layer; it never constructs query
shapes.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import importlib
import inspect
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from types import SimpleNamespace
from typing import Any, Callable, Iterable

import pytest
from fastapi import HTTPException

import database.conversations as conversations_db
import database.users as users_db
import routers.conversations as conversations_router
import routers.developer as developer_router
import routers.google_calendar as google_calendar_router
import routers.integration as integration_router
import routers.search as search_router
import routers.users as users_router
import utils.app_integrations as app_integrations
import utils.apps as apps_utils
import utils.conversations.meeting_context_pack as meeting_context_pack
import utils.imports.limitless as limitless
import utils.llm.fair_use_classifier as fair_use_classifier
import utils.llm.goals as llm_goals
import utils.other.notifications as notifications_utils
import utils.people_stats as people_stats
import utils.retrieval.tool_services.conversations as tool_conversations
import utils.retrieval.tools.conversation_tools as conversation_tools
import utils.speaker_tag_prompts.service as speaker_tag_service
import utils.wrapped.generate_2025 as wrapped_2025
from models.conversation import SearchRequest
from tests.support.firestore_conversation_profiles import PROFILES
from tests.support.firestore_query_drivers import CallerProfile, FROZEN_LATER, FROZEN_NOW


class CapturedCall(BaseException):
    """Aborts the owning function immediately after the query helper is bound."""


@dataclass(frozen=True)
class CallerWitness:
    """One real owning-function call-site binding pinned to named profiles."""

    key: str
    target: str
    patch_site: str
    profiles: tuple[str, ...]
    references: int
    run: Callable[[pytest.MonkeyPatch, 'HelperCapture'], None]
    abort: bool = True


@dataclass(frozen=True)
class HelperCapture:
    calls: list[dict[str, Any]]
    function: Callable[..., Any]


def install_capture(monkeypatch: pytest.MonkeyPatch, witness: CallerWitness) -> HelperCapture:
    """Patch the witness's import site with a recorder bound to the real helper signature."""
    module_name, _, attr = witness.patch_site.rpartition('.')
    owner_module = importlib.import_module(module_name)
    target_module = importlib.import_module(witness.target.rpartition('.')[0])
    signature = inspect.signature(getattr(target_module, witness.target.rpartition('.')[2]))
    calls: list[dict[str, Any]] = []
    result = 0 if attr == 'get_conversations_count' else []

    def capture(*args: Any, **kwargs: Any) -> Any:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        calls.append(dict(bound.arguments))
        if witness.abort:
            raise CapturedCall()
        return result

    monkeypatch.setattr(owner_module, attr, capture)
    return HelperCapture(calls=calls, function=capture)


def trial(capture: HelperCapture, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Invoke one accepted trial; the helper must be bound exactly once.

    Route/helper binding errors propagate — a trial that never reaches the
    helper (or reaches it twice) fails instead of being silently skipped.
    """
    before = len(capture.calls)
    with contextlib.suppress(CapturedCall):
        fn(*args, **kwargs)
    gained = len(capture.calls) - before
    assert gained == 1, f'expected exactly one helper call per trial, got {gained}: {args} {kwargs}'


def rejected_trial(capture: HelperCapture, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Invoke a rejected trial: HTTP 400 and zero helper calls."""
    before = len(capture.calls)
    with pytest.raises(HTTPException) as exc_info:
        fn(*args, **kwargs)
    assert exc_info.value.status_code == 400
    assert len(capture.calls) == before, 'rejected trial reached the query helper'


def _stub(monkeypatch: pytest.MonkeyPatch, owner: Any, name: str, value: Any) -> None:
    monkeypatch.setattr(owner, name, value, raising=False)


async def _inline_run_blocking(_executor: Any, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    return fn(*args, **kwargs)


def _normalized(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    return value


def _domain_accepts(expected: Any, actual: Any) -> bool:
    if isinstance(expected, datetime):
        return isinstance(actual, datetime)
    return _normalized(expected) == _normalized(actual)


def matching_profile_names(profiles: Iterable[CallerProfile], captured: dict[str, Any]) -> set[str]:
    """Return every profile whose domains cover the bound call."""
    return {
        profile.name
        for profile in profiles
        if all(
            key in captured and any(_domain_accepts(value, captured[key]) for value in profile.domains[key])
            for key in profile.domains
        )
    }


def matching_profile_name(profiles: Iterable[CallerProfile], captured: dict[str, Any]) -> str | None:
    """Return the first profile whose domains cover the bound call."""
    matched = matching_profile_names(profiles, captured)
    return next(iter(matched), None)


def matching_profile(target: str, captured: dict[str, Any], names: tuple[str, ...]) -> str | None:
    """Return the first named profile whose domains cover the bound call."""
    allowed = {profile.name: profile for profile in PROFILES[target]}
    return matching_profile_name((allowed[name] for name in names), captured)


_DATE_PAIRS = tuple(product((None, FROZEN_NOW), (None, FROZEN_LATER)))
_SOURCES_QUERY = (None, 'omi', 'friend,omi')
_DISCARDED = (False, True)
_FOLDER = (None, 'folder-1')
_STARRED = (None, False, True)


def _run_main_list(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    for statuses, sources in (
        ('completed', _SOURCES_QUERY),
        ('', (None, 'omi')),
        ('processing,completed', (None, 'omi')),
        ('processing,completed', ('friend,omi',)),
    ):
        for source in sources:
            for discarded in _DISCARDED:
                for folder in _FOLDER:
                    for starred in _STARRED:
                        for start, end in _DATE_PAIRS:
                            call = lambda: conversations_router.get_conversations(
                                request=None,
                                response=None,
                                limit=25,
                                offset=0,
                                include_discarded=discarded,
                                statuses=statuses,
                                sources=source,
                                start_date=start,
                                end_date=end,
                                folder_id=folder,
                                starred=starred,
                                uid='u1',
                            )
                            if source == 'friend,omi' and statuses == 'processing,completed':
                                rejected_trial(capture, call)
                            else:
                                trial(capture, call)


def _run_main_count(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    for statuses in (None, '', 'completed', 'processing,completed'):
        for source in _SOURCES_QUERY:
            for discarded in _DISCARDED:
                for folder in _FOLDER:
                    for starred in _STARRED:
                        for start, end in _DATE_PAIRS:
                            call = lambda: conversations_router.get_conversations_count(
                                statuses=statuses,
                                include_discarded=discarded,
                                start_date=start,
                                end_date=end,
                                folder_id=folder,
                                starred=starred,
                                sources=source,
                                uid='u1',
                            )
                            if source == 'friend,omi' and statuses not in (None, '', 'completed'):
                                rejected_trial(capture, call)
                            else:
                                trial(capture, call)


def _run_speaker_browse(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, users_db, 'get_person', lambda uid, person_id: {'id': person_id, 'name': 'Speaker'})
    _stub(
        monkeypatch,
        conversations_router,
        'browse_conversations_by_speaker',
        lambda fetch, speaker_id, **kwargs: list(fetch(50, 0)),
    )
    for discarded in _DISCARDED:
        for start, end in _DATE_PAIRS:
            request = SearchRequest(
                query='',
                speaker_id='person-1',
                include_discarded=discarded,
                start_date=start.isoformat() if start else None,
                end_date=end.isoformat() if end else None,
            )
            trial(capture, conversations_router.search_conversations_endpoint, request, uid='u1')


def _run_developer_list(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    auth = SimpleNamespace(uid='u1')
    for categories in (None, 'personal', 'personal,technology'):
        for folder in _FOLDER:
            for starred in _STARRED:
                for start, end in _DATE_PAIRS:
                    trial(
                        capture,
                        developer_router.get_conversations,
                        start_date=start,
                        end_date=end,
                        categories=categories,
                        limit=25,
                        offset=0,
                        include_transcript=False,
                        folder_id=folder,
                        starred=starred,
                        uid=auth,
                        request=None,
                    )


def _run_integration_list(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, integration_router, 'verify_api_key', lambda app_id, key: True)
    _stub(monkeypatch, integration_router.apps_db, 'get_app_by_id_db', lambda app_id: {'id': app_id})
    _stub(monkeypatch, integration_router.redis_db, 'get_enabled_apps', lambda uid: {'app-1'})
    _stub(monkeypatch, integration_router.apps_utils, 'app_can_read_conversations', lambda app: True)
    for statuses in ([], ['completed'], ['processing', 'completed']):
        for discarded in _DISCARDED:
            for start, end in _DATE_PAIRS:
                trial(
                    capture,
                    integration_router.get_conversations_via_integration,
                    request=None,
                    app_id='app-1',
                    uid='u1',
                    limit=50,
                    offset=0,
                    include_discarded=discarded,
                    statuses=statuses,
                    start_date=start,
                    end_date=end,
                    max_transcript_segments=0,
                    authorization='Bearer key',
                )


def _run_search_overview(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, search_router, 'run_blocking', _inline_run_blocking)
    _stub(monkeypatch, search_router, '_list_folders', lambda uid: [{'id': 'folder-1', 'name': 'F'}])
    _stub(monkeypatch, search_router.daily_summaries_db, 'get_summaries_count', lambda uid: 0)
    _stub(monkeypatch, search_router.memories_db, 'count_default_visible_memories', lambda uid: 0)
    _stub(monkeypatch, users_db, 'count_people', lambda uid: 0)
    _stub(monkeypatch, conversations_db, 'count_conversations_with_geolocation', lambda uid: 0)
    asyncio.run(search_router.get_search_overview(uid='u1'))
    assert len(capture.calls) == 2, f'expected the starred and folder count call sites, got {capture.calls}'


def _run_people_stats(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, users_router, 'get_people', lambda uid: [{'id': 'p1', 'name': 'Person'}])
    _stub(monkeypatch, people_stats, 'collect_people_stats', lambda fetch: (fetch(50, 0), {})[1])
    _stub(monkeypatch, people_stats, 'apply_people_stats', lambda people, stats: None)
    trial(capture, users_router.get_all_people, include_speech_samples=False, include_stats=True, uid='u1')


def _run_daily_summary_regenerate(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, users_router, 'enforce_chat_quota', lambda *a, **k: None)
    _stub(monkeypatch, users_router.notification_db, 'get_user_time_zone', lambda uid: None)
    _stub(
        monkeypatch,
        users_router.daily_summaries_db,
        'get_daily_summary',
        lambda uid, summary_id: {'id': summary_id, 'date': '2026-01-15'},
    )
    _stub(monkeypatch, users_router, 'get_generic_cache', lambda key: None)
    _stub(monkeypatch, users_router, 'set_generic_cache', lambda *a, **k: None)
    trial(capture, users_router.regenerate_daily_summary, 'sum-1', uid='u1', x_app_platform=None)


def _run_daily_summary_test_route(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, users_router, 'enforce_chat_quota', lambda *a, **k: None)
    _stub(monkeypatch, users_router.notification_db, 'get_user_time_zone', lambda uid: None)
    _stub(monkeypatch, users_router.notification_db, 'get_all_tokens', lambda uid: ['tok'])
    trial(capture, users_router.test_daily_summary, request=None, uid='u1', x_app_platform=None)


def _run_mentor_notification(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    frequency = next(key for key, value in app_integrations.FREQUENCY_TO_BASE_THRESHOLD.items() if value is not None)
    _stub(monkeypatch, app_integrations, 'get_mentor_notification_frequency', lambda uid: frequency)
    _stub(monkeypatch, app_integrations.mem_db, 'get_proactive_noti_sent_at', lambda uid, kind: None)
    _stub(monkeypatch, app_integrations.redis_db, 'get_proactive_noti_sent_at', lambda uid, kind: None)
    _stub(monkeypatch, app_integrations, '_proactive_daily_cap_reached', lambda uid: False)
    _stub(monkeypatch, app_integrations, '_mentor_gate_debounce_enabled', lambda: False)
    _stub(monkeypatch, app_integrations, 'get_prompt_memories', lambda uid: ('User', []))
    _stub(monkeypatch, app_integrations, 'get_user_goals', lambda uid, limit=3: [])
    _stub(monkeypatch, app_integrations, 'current_date_for_uid', lambda uid: '2026-01-15')
    _stub(monkeypatch, app_integrations, 'get_app_messages', lambda uid, kind, limit=20: [])
    _stub(monkeypatch, app_integrations, 'track_usage', lambda *a, **k: contextlib.nullcontext())
    relevance = SimpleNamespace(is_relevant=True, relevance_score=999.0, context_summary='', reasoning='')
    _stub(monkeypatch, app_integrations, 'evaluate_relevance', lambda **kwargs: relevance)
    _stub(monkeypatch, app_integrations, 'generate_embedding', lambda text: [])
    _stub(monkeypatch, app_integrations, 'query_vectors_by_metadata', lambda *a, **k: [])
    trial(capture, app_integrations._process_mentor_proactive_notification, 'u1', [{'text': 'hi'}])


def _stub_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, apps_utils, 'run_blocking', _inline_run_blocking)
    _stub(
        monkeypatch,
        apps_utils,
        'MemoryService',
        lambda **kwargs: SimpleNamespace(read=lambda *a, **k: []),
    )
    _stub(monkeypatch, apps_utils, 'get_user_name', lambda uid: 'User')


def _run_persona_create(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub_persona(monkeypatch)
    with contextlib.suppress(CapturedCall):
        asyncio.run(apps_utils.generate_persona_prompt('u1', {'connected_accounts': {}}))
    assert len(capture.calls) == 1


def _run_persona_update(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub_persona(monkeypatch)
    with contextlib.suppress(CapturedCall):
        asyncio.run(apps_utils.update_persona_prompt({'uid': 'u1', 'connected_accounts': {}}))
    assert len(capture.calls) == 1


def _run_prior_meetings(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, meeting_context_pack.calendar_db, 'list_meetings', lambda *a, **k: [])
    roster = SimpleNamespace(entries=[SimpleNamespace(kind='human', display_name='Alice', email=None, person_id=None)])
    trial(
        capture,
        meeting_context_pack._gather_prior_meetings,
        'u1',
        SimpleNamespace(),
        roster,
        FROZEN_NOW,
        None,
    )


def _run_limitless_lookup(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, limitless.find_legacy_limitless_conversation_id, 'u1', FROZEN_NOW)


def _run_fair_use(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    trial(capture, fair_use_classifier._prepare_conversation_summaries, 'u1')


def _run_goal_context(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, llm_goals, 'vector_search', lambda query, uid, k: [])
    trial(capture, llm_goals._get_goal_context, 'u1', 'title')


def _run_daily_summary_generation(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, notifications_utils, 'try_acquire_daily_summary_lock', lambda uid, date_str: True)
    _stub(
        monkeypatch,
        notifications_utils.daily_summaries_db,
        'get_daily_summary_by_date',
        lambda uid, date_str: None,
    )
    trial(
        capture,
        notifications_utils._generate_and_store_daily_summary,
        'u1',
        '2026-01-15',
        FROZEN_NOW,
        FROZEN_LATER,
    )


def _run_tool_service(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    for statuses in (None, '', 'completed', 'processing,completed'):
        for discarded in _DISCARDED:
            for start, end in _DATE_PAIRS:
                trial(
                    capture,
                    tool_conversations.get_conversations_text,
                    'u1',
                    start_date=start.isoformat() if start else None,
                    end_date=end.isoformat() if end else None,
                    include_discarded=discarded,
                    statuses=statuses,
                )


def _run_chat_tool(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    config = {'configurable': {'user_id': 'u1'}}
    for statuses in (None, '', 'completed', 'processing,completed'):
        for discarded in _DISCARDED:
            for start, end in _DATE_PAIRS:
                trial(
                    capture,
                    conversation_tools.get_conversations_tool.invoke,
                    {
                        'start_date': start.isoformat() if start else None,
                        'end_date': end.isoformat() if end else None,
                        'include_discarded': discarded,
                        'statuses': statuses,
                        'max_transcript_segments': 0,
                    },
                    config=config,
                )


def _run_speaker_prompts(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(
        monkeypatch,
        speaker_tag_service.voice_profiles_db,
        'get_voice_profile_context',
        lambda uid: ({'save_other_voice_profiles': False, 'speaker_tag_prompts_enabled': True}, False),
    )
    _stub(monkeypatch, speaker_tag_service.voice_profiles_db, 'get_tag_prompt_state', lambda uid: {})
    _stub(monkeypatch, speaker_tag_service, 'named_speaker_prompts_allowed', lambda uid: True)
    _stub(monkeypatch, users_db, 'get_people', lambda uid: [])
    trial(capture, speaker_tag_service.get_prompts, 'u1', now=FROZEN_NOW)


def _run_calendar_gaps(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, google_calendar_router, 'run_blocking', _inline_run_blocking)
    _stub(monkeypatch, google_calendar_router, '_get_google_calendar_token', lambda uid: ('token', None))
    _stub(monkeypatch, google_calendar_router, 'emit_sync_attempted', lambda *a, **k: None)
    _stub(monkeypatch, google_calendar_router, 'emit_sync_succeeded', lambda *a, **k: None)
    _stub(monkeypatch, google_calendar_router, 'emit_sync_failed', lambda *a, **k: None)

    async def events(**kwargs: Any) -> list:
        return []

    _stub(monkeypatch, google_calendar_router, 'get_google_calendar_events', events)

    def call() -> None:
        asyncio.run(google_calendar_router.get_calendar_capture_gaps(start=FROZEN_NOW, end=FROZEN_LATER, uid='u1'))

    trial(capture, call)


def _run_wrapped(monkeypatch: pytest.MonkeyPatch, capture: HelperCapture) -> None:
    _stub(monkeypatch, wrapped_2025, '_update_progress', lambda *a, **k: None)
    trial(capture, wrapped_2025.generate_wrapped_2025, 'u1')


WITNESSES: dict[str, CallerWitness] = {
    witness.key: witness
    for witness in (
        CallerWitness(
            'routers/conversations.py:get_conversations:database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            ('main-list-single-status', 'main-list-default-or-multi-status'),
            1,
            _run_main_list,
        ),
        CallerWitness(
            'routers/conversations.py:get_conversations_count:database.conversations.get_conversations_count',
            'database.conversations.get_conversations_count',
            'database.conversations.get_conversations_count',
            ('main-count-all-statuses', 'main-count-single-status', 'main-count-multi-status'),
            1,
            _run_main_count,
        ),
        CallerWitness(
            'routers/conversations.py:search_conversations_endpoint:database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            ('speaker-search-fallback',),
            1,
            _run_speaker_browse,
        ),
        CallerWitness(
            'routers/developer.py:get_conversations:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('developer-list',),
            1,
            _run_developer_list,
        ),
        CallerWitness(
            'routers/google_calendar.py:get_calendar_capture_gaps:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('calendar-capture-gaps',),
            1,
            _run_calendar_gaps,
        ),
        CallerWitness(
            'routers/integration.py:get_conversations_via_integration:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('integration-list',),
            1,
            _run_integration_list,
        ),
        CallerWitness(
            'routers/search.py:get_search_overview:database.conversations.get_conversations_count',
            'database.conversations.get_conversations_count',
            'database.conversations.get_conversations_count',
            ('search-overview-starred', 'search-overview-folder'),
            2,
            _run_search_overview,
            abort=False,
        ),
        CallerWitness(
            'routers/users.py:get_all_people:database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            ('people-stats',),
            1,
            _run_people_stats,
        ),
        CallerWitness(
            'routers/users.py:regenerate_daily_summary:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('daily-summary-regenerate',),
            1,
            _run_daily_summary_regenerate,
        ),
        CallerWitness(
            'routers/users.py:test_daily_summary:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('daily-summary-test',),
            1,
            _run_daily_summary_test_route,
        ),
        CallerWitness(
            'utils/app_integrations.py:_process_mentor_proactive_notification:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('mentor-notification',),
            1,
            _run_mentor_notification,
        ),
        CallerWitness(
            'utils/apps.py:generate_persona_prompt:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'utils.apps.get_conversations',
            ('persona-create',),
            1,
            _run_persona_create,
        ),
        CallerWitness(
            'utils/apps.py:update_persona_prompt:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'utils.apps.get_conversations',
            ('persona-update',),
            1,
            _run_persona_update,
        ),
        CallerWitness(
            'utils/conversations/meeting_context_pack.py:_gather_prior_meetings:database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            ('prior-meeting-context',),
            1,
            _run_prior_meetings,
        ),
        CallerWitness(
            'utils/imports/limitless.py:find_legacy_limitless_conversation_id:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('limitless-legacy-lookup',),
            1,
            _run_limitless_lookup,
        ),
        CallerWitness(
            'utils/llm/fair_use_classifier.py:_prepare_conversation_summaries:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('fair-use-classification',),
            1,
            _run_fair_use,
        ),
        CallerWitness(
            'utils/llm/goals.py:_get_goal_context:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('goal-context',),
            1,
            _run_goal_context,
        ),
        CallerWitness(
            'utils/other/notifications.py:_generate_and_store_daily_summary:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('daily-summary-generation',),
            1,
            _run_daily_summary_generation,
        ),
        CallerWitness(
            'utils/retrieval/tool_services/conversations.py:get_conversations_text:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('tool-service',),
            1,
            _run_tool_service,
        ),
        CallerWitness(
            'utils/retrieval/tools/conversation_tools.py:get_conversations_tool:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('chat-retrieval',),
            1,
            _run_chat_tool,
        ),
        CallerWitness(
            'utils/speaker_tag_prompts/service.py:get_prompts:database.conversations.get_conversations',
            'database.conversations.get_conversations',
            'database.conversations.get_conversations',
            ('speaker-prompts',),
            1,
            _run_speaker_prompts,
        ),
        CallerWitness(
            'utils/wrapped/generate_2025.py:generate_wrapped_2025:database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            'database.conversations.get_conversations_without_photos',
            ('wrapped-2025',),
            1,
            _run_wrapped,
        ),
    )
}


def witness_completeness_errors(
    discovered: dict[str, dict[str, Any]], witnesses: dict[str, CallerWitness] | None = None
) -> list[str]:
    """Return violations: discovered bindings without witnesses, or stale witnesses."""
    witnesses = WITNESSES if witnesses is None else witnesses
    errors: list[str] = []
    for key, row in discovered.items():
        witness = witnesses.get(key)
        if witness is None:
            errors.append(f'{key}: discovered serving caller has no named runtime witness')
        elif witness.references != row['references']:
            errors.append(f"{key}: discovered {row['references']} references, witness expects {witness.references}")
        elif witness.target != row['target']:
            errors.append(f"{key}: discovered target {row['target']} != witness target {witness.target}")
    for key in sorted(set(witnesses) - set(discovered)):
        errors.append(f'{key}: witness exists for a caller that is no longer discovered')
    return errors
