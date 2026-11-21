"""Which startup work this backend process runs (``OMI_PROCESS_ROLE``).

Independent of ``OMI_ROLE`` (router selection, ``app_roles.py``) and of the batch kill
switches. Unset or ``all`` keeps the full ``main.startup_event`` set. ``projection_pump``
(only on the ``backend-projection-pump`` Cloud Run service) keeps the projection pump and
what the projector needs, and never starts or leases the FSR reconcilers, so a pump on an
older SHA than the trains cannot run deletion, purge or finalization work. Turning the pump
flag off does not restore those reconcilers; only unsetting this role does. Any other value
fails startup. Keep and skip sets: docs/listen_pusher_pipeline/changes/
2026-11-19-projection-pump-deploy-target.md ("Startup isolation").
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Mapping

PROCESS_ROLE_ENV = 'OMI_PROCESS_ROLE'
SERVING_ENV = 'BATCH_PIPELINE_SERVING_ENABLED'


class ProcessRole(StrEnum):
    ALL = 'all'
    PROJECTION_PUMP = 'projection_pump'


class ProcessRoleConfigError(ValueError):
    pass


def process_role_from_env(environ: Mapping[str, str] | None = None) -> ProcessRole:
    """Unset means ``all``; an unknown value raises rather than picking a startup set."""

    raw = (os.environ if environ is None else environ).get(PROCESS_ROLE_ENV, '').strip().lower()
    if not raw:
        return ProcessRole.ALL
    try:
        return ProcessRole(raw)
    except ValueError as exc:
        allowed = ', '.join(role.value for role in ProcessRole)
        raise ProcessRoleConfigError(f'{PROCESS_ROLE_ENV}={raw!r} is not a process role ({allowed})') from exc


def startup_process_role(environ: Mapping[str, str] | None = None) -> ProcessRole:
    """Resolve the role for ``startup_event`` and refuse a pump that would run the serving loops."""

    env = os.environ if environ is None else environ
    role = process_role_from_env(env)
    # Same parse as utils.batch_pipeline.serving.start_serving_from_env.
    if role is ProcessRole.PROJECTION_PUMP and env.get(SERVING_ENV, 'false').strip().lower() == 'true':
        raise ProcessRoleConfigError(f'{PROCESS_ROLE_ENV}={role.value} refuses {SERVING_ENV}=true')
    return role


def is_projection_pump_process(environ: Mapping[str, str] | None = None) -> bool:
    return process_role_from_env(environ) is ProcessRole.PROJECTION_PUMP
