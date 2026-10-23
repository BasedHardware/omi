"""Deployable roles inside the one backend image (B8, ruling 2).

`OMI_ROLE` selects which routers a process mounts. The default `all` mounts every
router in today's order, so an unset or `all` role is behaviour-neutral. `main.py`
mounts through `mount_routers`; this module holds the static router imports.

Role membership is provisional until the B9 route census: a service may move off
`all` only when every path it received in the census window is mounted by its
role. Invariants (tests/unit/test_app_roles_route_census.py):
- the `all` mount order equals main.py's router order;
- every router belongs to at least one non-`all` role;
- every Cloud Tasks target route (TaskEdges) and every Scheduler target path is
  mounted by `workers`;
- every websocket route is mounted by `realtime`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import ModuleType
from typing import Any

# The route table owns the router imports (static, so the image source closure and import-time
# checks still see every router). main.py imports this module after its env/credential setup,
# at the position its own router imports used to have, so import order is unchanged.
from routers import messaging
from routers import (
    fleet_telemetry,
    budget_choice,
    candidate_integration_sweep,
    chat_receipts,
    dream_cohort,
    dream_report,
    dream_sweep,
    review,
    proactivity,
    chat,
    chat_video,
    firmware,
    static_map,
    transcribe,
    omni_relay,
    auto_model,
    notifications,
    speech_profile,
    speaker_tag_prompts,
    speaker_labels,
    people,
    agents,
    users,
    support,
    trends,
    sync,
    batch_pipeline,
    batch_provider_stt,
    enrichment,
    apps,
    payment,
    storefront,
    integration,
    conversations,
    conversation_mutations,
    memories,
    api_key_management,
    mcp,
    mcp_sse,
    oauth,
    auth,
    action_items,
    account_cutover,
    candidates,
    chat_first,
    chat_first_e2e,
    daily_summary_e2e,
    task_integrations,
    integrations,
    x_connector,
    other,
    developer,
    developer_key,
    updates,
    calendar_meetings,
    google_calendar,
    calendar_onboarding,
    imports,
    knowledge_graph,
    wrapped,
    folders,
    search,
    goals,
    workstreams,
    announcements,
    phone_calls,
    agent_tools,
    tools,
    metrics,
    fair_use_admin,
    feedback_admin,
    staged_tasks,
    focus_sessions,
    advice,
    chat_sessions,
    chat_generation,
    desktop_agent_vm,
    desktop_chat,
    desktop_core,
    desktop_prompts,
    desktop_proxy,
    desktop_task_gate,
    desktop_realtime,
    desktop_screen_crisp,
    frame_requests,
    retired_app_client_contracts,
    referrals,
    desktop_tts_updates,
    scores,
    stt,
    tts,
    memory_admin,
    memory_product,
    task_recommendations,
    conversation_finalization,
    pending_work,
    episodes,
    boundary_evidence,
    commitment_followup,
    public_shared_conversation_chat,
    screen_frames,
    csat,
    email_preferences,
    mobile_feedback,
    device_diagnostics,
    client_telemetry,
)


class AppRole(StrEnum):
    ALL = 'all'
    API = 'api'
    WORKERS = 'workers'
    REALTIME = 'realtime'


ROLE_ENV = 'OMI_ROLE'
DEFAULT_ROLE = AppRole.ALL

API = frozenset({AppRole.API})
API_WORKERS = frozenset({AppRole.API, AppRole.WORKERS})
API_REALTIME = frozenset({AppRole.API, AppRole.REALTIME})
EVERY = frozenset({AppRole.API, AppRole.WORKERS, AppRole.REALTIME})


@dataclass(frozen=True)
class Mount:
    router_module: ModuleType
    attr: str = 'router'
    roles: frozenset[AppRole] = API
    harness_only: bool = False  # mounted only in the chat-first E2E harness runtime

    @property
    def module(self) -> str:
        return self.router_module.__name__.rsplit('.', 1)[-1]

    @property
    def key(self) -> str:
        return f'{self.module}.{self.attr}'


# Order is significant: FastAPI matches the first registered route. Keep it equal to
# the pre-B8 include order in main.py (asserted by the census test).
ROUTER_MOUNTS: tuple[Mount, ...] = (
    Mount(budget_choice),
    Mount(messaging),
    Mount(proactivity),
    Mount(dream_cohort),
    Mount(dream_report),
    Mount(dream_sweep, roles=API_WORKERS),  # Scheduler: /v2/dream-agent/sweep, canary
    Mount(candidate_integration_sweep, roles=API_WORKERS),  # Scheduler: /v2/candidate-integrations/sweep
    Mount(transcribe, roles=API_REALTIME),  # /v4/listen websocket
    Mount(static_map),
    Mount(omni_relay, roles=API_REALTIME),  # websockets
    Mount(auto_model),
    Mount(conversations),
    Mount(conversation_mutations),
    Mount(public_shared_conversation_chat),
    Mount(action_items),
    Mount(account_cutover),
    Mount(candidates),
    Mount(chat_first),
    Mount(chat_first_e2e, harness_only=True),
    Mount(daily_summary_e2e, harness_only=True),
    Mount(task_integrations),
    Mount(integrations),
    Mount(x_connector),
    Mount(memories),
    Mount(chat, roles=API_REALTIME),  # websocket
    Mount(chat_receipts),
    Mount(chat_video),  # main #22839 via sync 14
    Mount(speech_profile),
    Mount(speaker_tag_prompts),
    Mount(speaker_labels),
    Mount(people),
    Mount(notifications),
    Mount(integration),
    Mount(agents),
    Mount(users, roles=API_WORKERS),  # Cloud Tasks: /v1/users/account-deletion-wipes/run
    Mount(support),
    Mount(referrals),
    Mount(csat),
    Mount(feedback_admin),
    Mount(email_preferences),
    Mount(mobile_feedback),
    Mount(device_diagnostics),
    Mount(desktop_prompts),
    Mount(conversation_finalization, roles=EVERY),  # Cloud Tasks; listen enqueues
    Mount(pending_work),
    Mount(boundary_evidence),
    Mount(episodes),  # main #22877 via sync 15 (same position as main.py)
    Mount(commitment_followup),
    Mount(trends),
    Mount(other, roles=EVERY),  # health and readiness
    Mount(firmware),
    Mount(updates),
    Mount(sync, roles=API_WORKERS),  # uploads (api) and Cloud Tasks /v2/sync-jobs/run (workers)
    Mount(batch_pipeline, roles=API_WORKERS),  # GPU worker RPC pull and recovery tasks
    Mount(enrichment, roles=API_WORKERS),  # Cloud Tasks /v2/enrichment/run (lane 9; contract (a) phase 1)
    Mount(batch_provider_stt, roles=API_WORKERS),  # Cloud Tasks /v2/batch-pipeline/provider-stt/run (lane 8)
    Mount(apps),
    Mount(calendar_meetings),
    Mount(google_calendar),
    Mount(calendar_onboarding),
    Mount(oauth),
    Mount(auth),
    Mount(payment),
    Mount(storefront),
    Mount(api_key_management, attr='mcp_router'),
    Mount(mcp),
    Mount(mcp_sse),
    Mount(api_key_management, attr='developer_router'),
    Mount(developer),
    Mount(developer_key),
    Mount(imports),
    Mount(wrapped),
    Mount(folders),
    Mount(search),
    Mount(knowledge_graph),
    Mount(goals),
    Mount(workstreams),
    Mount(announcements),
    Mount(phone_calls),
    Mount(agent_tools),
    Mount(tools),
    Mount(metrics, roles=EVERY),
    Mount(client_telemetry),
    Mount(fleet_telemetry),
    Mount(fair_use_admin),
    Mount(staged_tasks),
    Mount(focus_sessions),
    Mount(advice),
    Mount(chat_sessions),
    Mount(chat_generation),
    Mount(scores),
    Mount(stt),
    Mount(tts),
    Mount(memory_admin),
    Mount(memory_product),
    Mount(task_recommendations),
    Mount(desktop_core),
    Mount(desktop_agent_vm),
    Mount(desktop_chat),
    Mount(desktop_proxy),
    Mount(desktop_task_gate),
    Mount(desktop_realtime, roles=API_REALTIME),
    Mount(desktop_screen_crisp),
    Mount(frame_requests),
    Mount(retired_app_client_contracts),
    Mount(desktop_tts_updates),
    Mount(screen_frames),
    Mount(review),
)


class RoleConfigError(ValueError):
    pass


def role_from_env(environ: Mapping[str, str] | None = None) -> AppRole:
    """Resolve OMI_ROLE. Unset means `all`; an unknown value fails startup rather than mounting nothing."""

    raw = (os.environ if environ is None else environ).get(ROLE_ENV, '').strip().lower()
    if not raw:
        return DEFAULT_ROLE
    try:
        return AppRole(raw)
    except ValueError as exc:
        allowed = ', '.join(role.value for role in AppRole)
        raise RoleConfigError(f'{ROLE_ENV}={raw!r} is not a role ({allowed})') from exc


def mounts_for(role: AppRole, *, include_harness: bool = False) -> tuple[Mount, ...]:
    return tuple(
        mount
        for mount in ROUTER_MOUNTS
        if (include_harness or not mount.harness_only) and (role is AppRole.ALL or role in mount.roles)
    )


def mount_routers(app: Any, role: AppRole, *, include_harness: bool = False) -> int:
    """Include the role's routers on `app` in ROUTER_MOUNTS order. Returns the count."""

    mounts = mounts_for(role, include_harness=include_harness)
    for mount in mounts:
        app.include_router(getattr(mount.router_module, mount.attr))
    return len(mounts)
