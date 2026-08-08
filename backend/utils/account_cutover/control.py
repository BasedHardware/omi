"""Build the authenticated account-cutover control projection."""

from __future__ import annotations

from typing import Mapping, Optional

from config.account_cutover import (
    DEFAULT_API_GENERATION,
    DEFAULT_UI_GENERATION,
    MINIMUM_SUPPORTED_BUILDS,
)
from models.account_cutover import (
    AccountCutoverClientAction,
    AccountCutoverControl,
    AccountCutoverManifestSummary,
    AccountCutoverRecord,
    AccountCutoverState,
    OfflineQueueInstruction,
    PlatformMinimumBuild,
)
from utils.account_cutover.fence import legacy_writes_allowed_for_state


def parse_client_build(raw: Optional[str]) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Mobile historically sends ``version+build`` in X-App-Version.
    if '+' in text:
        text = text.rsplit('+', 1)[-1]
    try:
        value = int(text)
    except ValueError:
        return None
    return value if value >= 0 else None


def minimum_builds_projection(
    overrides: Optional[Mapping[str, int]] = None,
) -> tuple[PlatformMinimumBuild, ...]:
    merged = dict(MINIMUM_SUPPORTED_BUILDS)
    if overrides:
        for platform, build in overrides.items():
            if build >= 0:
                merged[str(platform).strip().lower()] = build
    return tuple(
        PlatformMinimumBuild(platform=platform, minimum_supported_build=build)
        for platform, build in sorted(merged.items())
    )


def resolve_client_action(
    *,
    record: AccountCutoverRecord,
    platform: Optional[str],
    client_build: Optional[int],
    minimum_builds: Optional[Mapping[str, int]] = None,
) -> AccountCutoverClientAction:
    platform_key = (platform or '').strip().lower() or None
    floors = dict(MINIMUM_SUPPORTED_BUILDS)
    if minimum_builds:
        floors.update({str(k).strip().lower(): int(v) for k, v in minimum_builds.items()})

    if platform_key and platform_key in floors:
        floor = floors[platform_key]
        if floor > 0 and (client_build is None or client_build < floor):
            return AccountCutoverClientAction.force_upgrade

    if record.state in {AccountCutoverState.migrating, AccountCutoverState.rolled_back_stranded}:
        return AccountCutoverClientAction.migration_maintenance

    # Keep ``new`` on maintenance until a destination route is actually bound.
    # This foundation never binds one, so product shells stay blocked.
    if record.state == AccountCutoverState.new and record.destination_backend_bound is not True:
        return AccountCutoverClientAction.migration_maintenance

    return AccountCutoverClientAction.none


def product_traffic_allowed(
    *,
    record: AccountCutoverRecord,
    client_action: AccountCutoverClientAction,
) -> bool:
    if client_action != AccountCutoverClientAction.none:
        return False
    if record.state == AccountCutoverState.migrating:
        return False
    # No destination bridge route yet: never reopen the legacy product plane for
    # ``new`` accounts until ``destination_backend_bound`` is honest.
    if record.state == AccountCutoverState.new and record.destination_backend_bound is not True:
        return False
    return True


def build_account_cutover_control(
    record: AccountCutoverRecord,
    *,
    platform: Optional[str] = None,
    client_build: Optional[int] = None,
    x_app_build: Optional[str] = None,
    x_app_version: Optional[str] = None,
    minimum_builds: Optional[Mapping[str, int]] = None,
) -> AccountCutoverControl:
    """Project persisted cutover state into the stable client control contract."""

    build = client_build
    if build is None:
        # Preserve an explicit parsed build of 0; only fall back when absent/malformed.
        parsed_build = parse_client_build(x_app_build)
        build = parsed_build if parsed_build is not None else parse_client_build(x_app_version)

    builds = minimum_builds_projection(minimum_builds)
    action = resolve_client_action(
        record=record,
        platform=platform,
        client_build=build,
        minimum_builds=minimum_builds,
    )
    legacy_writes = legacy_writes_allowed_for_state(record.state) and action == AccountCutoverClientAction.none
    traffic = product_traffic_allowed(record=record, client_action=action)

    ui_generation = record.ui_generation
    api_generation = record.api_generation
    if record.state == AccountCutoverState.legacy:
        ui_generation = DEFAULT_UI_GENERATION
        api_generation = DEFAULT_API_GENERATION

    offline = record.offline_queue_instruction
    if (
        record.state in {AccountCutoverState.migrating, AccountCutoverState.new}
        and offline != OfflineQueueInstruction.quarantine
    ):
        # Migrating/new always project quarantine so clients do not attempt a
        # drain that server enforcement cannot accept. Stranded may still show
        # prepare_offline_drain instructions before a later begin.
        offline = OfflineQueueInstruction.quarantine

    return AccountCutoverControl(
        state=record.state,
        account_generation=record.account_generation,
        ui_generation=ui_generation,
        api_generation=api_generation,
        client_action=action,
        offline_queue_instruction=offline,
        stranded_new_data=record.stranded_new_data,
        legacy_writes_allowed=legacy_writes,
        product_traffic_allowed=traffic,
        auth_bootstrap_reachable=True,
        minimum_supported_builds=builds,
        migration=AccountCutoverManifestSummary(
            manifest_id=record.manifest_id,
            checkpoint_phase=record.checkpoint_phase,
            checkpoint_token=record.checkpoint_token,
            destination_backend_bound=record.destination_backend_bound,
            stranded_new_data=record.stranded_new_data,
        ),
    )


__all__ = [
    'build_account_cutover_control',
    'minimum_builds_projection',
    'parse_client_build',
    'product_traffic_allowed',
    'resolve_client_action',
]
