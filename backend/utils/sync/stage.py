"""Strict runtime stage boundary for shared sync persistence and task routes."""

from __future__ import annotations

import logging
import os

from fastapi import HTTPException

from utils.env_loader import VALID_STAGES

logger = logging.getLogger(__name__)


class InvalidSyncStage(ValueError):
    """Sync state cannot be addressed without an explicit known stage."""


def current_stage() -> str:
    stage = os.getenv('OMI_ENV_STAGE', '').strip().lower()
    if stage not in VALID_STAGES:
        logger.error('event=sync_runtime_stage outcome=invalid_config')
        raise InvalidSyncStage('sync runtime stage must be explicit and known')
    return stage


def production_stage() -> bool:
    return current_stage() == 'prod'


def nonproduction_stage() -> bool:
    return current_stage() != 'prod'


def redis_key(key: str) -> str:
    stage = current_stage()
    return key if stage == 'prod' else f'{stage}:{key}'


def collection_name(name: str) -> str:
    stage = current_stage()
    return name if stage == 'prod' else f'{name}_{stage}'


def require_http_stage() -> None:
    try:
        current_stage()
    except InvalidSyncStage as error:
        raise HTTPException(status_code=503, detail='Sync runtime stage is unavailable') from error
