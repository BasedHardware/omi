"""Internal endpoints for the app-review visibility lifecycle."""

from __future__ import annotations

import hmac
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from database.firestore_read_origin import read_origin
from services.app_review_config_lifecycle import (
    SECRET_NAMES,
    StoreCredentialsUnavailable,
    load_secret,
    report_lifecycle_alert,
    run_app_review_config_sweep,
    submit_review_version,
)
from utils.cloud_tasks import verify_cloud_tasks_oidc

router = APIRouter()
_VERSION_PATTERN = re.compile(r'^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$')
_VERSION_CODE_PATTERN = re.compile(r'^[1-9][0-9]{0,9}$')


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')

    platform: Literal['ios', 'android']
    version: str = Field(min_length=5, max_length=32)
    version_code: str | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode='after')
    def validate_identity(self) -> 'ReviewSubmission':
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise ValueError('version must be X.Y.Z')
        if self.platform == 'android':
            if self.version_code is None or not _VERSION_CODE_PATTERN.fullmatch(self.version_code):
                raise ValueError('Android submission requires a positive numeric version_code')
        elif self.version_code is not None:
            raise ValueError('version_code is only valid for Android submissions')
        return self


@router.post('/v2/internal/app-review-config/submissions', include_in_schema=False)
def record_review_submission(
    body: ReviewSubmission,
    submission_token: str | None = Header(default=None, alias='X-Review-Config-Token'),
):
    try:
        expected = load_secret(SECRET_NAMES['submission'])
    except StoreCredentialsUnavailable:
        report_lifecycle_alert(
            body.platform, 'submission_token_unavailable', 'Codemagic submission receipt cannot be authenticated'
        )
        raise HTTPException(status_code=503, detail='submission receipt service unavailable') from None
    if not submission_token or not hmac.compare_digest(submission_token, expected):
        raise HTTPException(status_code=401, detail='invalid submission token')
    return submit_review_version(body.platform, body.version, body.version_code)


@router.post('/v2/app-review-config/sweep', include_in_schema=False)
@read_origin('job:app_review_config_sweep')
def sweep_app_review_config(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    return run_app_review_config_sweep()
