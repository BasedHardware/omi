"""Authenticated account-cutover bootstrap/control projection."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, Request

from database import account_cutover as account_cutover_db
from models.account_cutover import AccountCutoverControl
from utils.account_cutover.control import build_account_cutover_control
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth

router = APIRouter(prefix='/v1/account/cutover', tags=['account-cutover'])


@router.get('/control', response_model=AccountCutoverControl)
async def get_account_cutover_control(
    request: Request,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_app_build: Optional[str] = Header(None, alias='X-App-Build'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
) -> AccountCutoverControl:
    """Stable authenticated bootstrap projection for bridge clients.

    Always reachable for signed-in users, including while product traffic is
    fenced for migrating / force-upgrade / stranded states. Does not migrate
    any account; absent documents project as legacy.
    """

    del request  # Request retained for OpenAPI/middleware parity with other control routes.

    def _load() -> AccountCutoverControl:
        record = account_cutover_db.get_account_cutover_record(uid)
        return build_account_cutover_control(
            record,
            platform=x_app_platform,
            x_app_build=x_app_build,
            x_app_version=x_app_version,
        )

    return await run_blocking(db_executor, _load)


__all__ = ['router']
