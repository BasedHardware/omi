"""Desktop experiment enrollment (EXP-002).

Server-side assignment for the macOS desktop identity experiment, following the
ratified substrate (``backend/utils/experiments.py``): Firebase uid unit,
deterministic draw, idempotent persisted assignment, both arms enrolled in the
same code path before any treatment UI, intention-to-treat analysis.

Contract highlights (pre-registered in
``backend/docs/experiments/EXP-002-desktop-identity-memory-v1.md``):

- **Fail closed.** Any gate or persist failure returns control chrome and no
  assignment. A delivered-but-unrecorded treatment corrupts the control arm;
  an undelivered one is a lost data point.
- **Channel gate.** v1 enrolls only the Beta bundle. Stable and unknown
  bundles are refused without writing.
- **Version floor.** Binaries below the minimum are refused: they cannot
  render the arms they would be enrolled into.
- **Kill switch.** Server-side PostHog flags, tri-state fail-closed. Flag off
  paints control and leaves existing assignments in place.
- **One Firestore plane.** Assignments resolve through the data-plane seam so
  the dev desktop-backend (Beta) and the prod backend (Stable later) write the
  same ``experiments/{id}/assignments`` collection. If the plane cannot be
  established, enrollment is skipped rather than split across planes.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config.desktop_experiments import (
    EXP_002_ALLOWED_BUNDLE_IDS,
    EXP_002_ALLOWED_CHANNEL,
    EXP_002_ARMS,
    EXP_002_EXPERIMENT_ID,
    EXP_002_FLAG_KEY,
    EXP_002_KILL_SWITCH_FLAG_KEY,
    exp_002_min_app_version,
    known_experiment_ids,
    version_meets_floor,
)
from database._client import get_data_plane_firestore_client, get_firestore_client
from utils.executors import db_executor, run_blocking
from utils.experiments import enroll, existing_assignment
from utils.jit_rollout import PostHogJITFlagProvider, TriState
from utils.other.endpoints import get_current_user_uid

logger = logging.getLogger(__name__)

router = APIRouter()

_flag_provider = PostHogJITFlagProvider(
    rollout_flag_key=EXP_002_FLAG_KEY,
    kill_switch_flag_key=EXP_002_KILL_SWITCH_FLAG_KEY,
)


class DesktopExperimentEnrollRequest(BaseModel):
    experiment_id: str
    channel: str
    bundle_id: str
    app_version: str
    app_build: Optional[str] = None
    platform: str = 'macos'


class DesktopExperimentEnrollResponse(BaseModel):
    experiment_id: str
    variant: Optional[str] = None
    enrolled: bool = False
    newly_enrolled: bool = False
    # The client applies arm chrome only when this is true. False paints
    # control regardless of any persisted variant (kill switch, gate refusal,
    # or persist failure).
    chrome_enabled: bool = False
    reason: str = 'enrolled'


@dataclass(frozen=True)
class _GateDecision:
    allowed: bool
    reason: str


def _channel_gate(request: DesktopExperimentEnrollRequest) -> _GateDecision:
    if request.channel != EXP_002_ALLOWED_CHANNEL or request.bundle_id not in EXP_002_ALLOWED_BUNDLE_IDS:
        return _GateDecision(False, 'channel_not_allowed')
    if not version_meets_floor(request.app_version, exp_002_min_app_version()):
        return _GateDecision(False, 'app_version_below_minimum')
    return _GateDecision(True, 'gates_passed')


async def _experiment_flag_enabled(uid: str) -> bool:
    """Tri-state fail-closed read of the enrollment flags."""

    try:
        evaluation = await _flag_provider(uid)
    except Exception:
        logger.exception('desktop experiments: flag evaluation failed uid_present=%s', bool(uid))
        return False
    return evaluation.rollout == TriState.ENABLED and evaluation.kill_switch != TriState.ENABLED


def _assignments_client() -> Any:
    """The Firestore client that owns experiment assignments on this surface.

    The desktop-backend compute project differs from the customer data plane,
    so its ``db`` default would land assignments in the wrong project. The
    data-plane seam pins to the mounted customer plane (and refuses a
    mismatched configuration). The emulator harness keeps its local plane.
    """

    if os.getenv('FIRESTORE_EMULATOR_HOST'):
        return get_firestore_client()
    return get_data_plane_firestore_client()


def _plane_name(client: Any) -> str:
    project = getattr(client, 'project', None)
    return str(project) if project else 'unknown'


async def _persisted_variant(uid: str, client: Any) -> Optional[str]:
    record = await run_blocking(
        db_executor,
        existing_assignment,
        EXP_002_EXPERIMENT_ID,
        uid,
        firestore_client=client,
    )
    if record and record.get('variant'):
        return str(record['variant'])
    return None


@router.post('/v1/desktop/experiments/enroll')
async def enroll_desktop_experiment(
    request: DesktopExperimentEnrollRequest,
    uid: str = Depends(get_current_user_uid),
) -> DesktopExperimentEnrollResponse:
    if request.experiment_id not in known_experiment_ids():
        raise HTTPException(status_code=404, detail='Unknown experiment')

    gate = _channel_gate(request)
    if not gate.allowed:
        # Gated clients never receive arm chrome and are never written.
        logger.info(
            'desktop experiment enrollment refused experiment_id=%s uid_present=%s channel=%s '
            'bundle_id=%s app_version=%s reason=%s',
            request.experiment_id,
            bool(uid),
            request.channel,
            request.bundle_id,
            request.app_version,
            gate.reason,
        )
        return DesktopExperimentEnrollResponse(experiment_id=request.experiment_id, reason=gate.reason)

    flag_enabled = await _experiment_flag_enabled(uid)

    try:
        client = await run_blocking(db_executor, _assignments_client)
    except Exception:
        logger.exception(
            'desktop experiment enrollment plane unavailable experiment_id=%s uid_present=%s',
            request.experiment_id,
            bool(uid),
        )
        return DesktopExperimentEnrollResponse(
            experiment_id=request.experiment_id, reason='assignments_plane_unavailable'
        )

    plane = _plane_name(client)

    if not flag_enabled:
        # Kill switch: paint control, leave any existing assignment in place.
        variant = await _persisted_variant(uid, client)
        logger.info(
            'desktop experiment enrollment disabled experiment_id=%s uid_present=%s variant=%s plane=%s',
            request.experiment_id,
            bool(uid),
            variant or 'none',
            plane,
        )
        return DesktopExperimentEnrollResponse(
            experiment_id=request.experiment_id,
            variant=variant,
            enrolled=variant is not None,
            chrome_enabled=False,
            reason='kill_switch_off',
        )

    enrollment = await run_blocking(
        db_executor,
        enroll,
        experiment_id=EXP_002_EXPERIMENT_ID,
        uid=uid,
        arms=EXP_002_ARMS,
        eligibility={
            'channel': request.channel,
            'bundle_id': request.bundle_id,
            'app_version': request.app_version,
            'app_build': request.app_build,
            'plane': plane,
        },
        source='desktop',
        firestore_client=client,
    )

    if enrollment is None:
        # Persist failed: fail closed to control chrome, no variant delivered.
        logger.error(
            'desktop experiment enrollment persist failed experiment_id=%s uid_present=%s plane=%s',
            request.experiment_id,
            bool(uid),
            plane,
        )
        return DesktopExperimentEnrollResponse(experiment_id=request.experiment_id, reason='persist_failed')

    logger.info(
        'desktop experiment enrolled experiment_id=%s variant=%s newly_enrolled=%s plane=%s ' 'app_version=%s',
        request.experiment_id,
        enrollment.variant,
        enrollment.newly_enrolled,
        plane,
        request.app_version,
    )
    return DesktopExperimentEnrollResponse(
        experiment_id=request.experiment_id,
        variant=enrollment.variant,
        enrolled=True,
        newly_enrolled=enrollment.newly_enrolled,
        chrome_enabled=True,
        reason='enrolled',
    )
