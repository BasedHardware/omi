"""Internal endpoints for the app-review visibility lifecycle."""

from __future__ import annotations

import hmac
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from database.firestore_read_origin import read_origin
from services.app_review_config_lifecycle import (
    SubmissionConfigConflict,
    StoreCredentialsUnavailable,
    is_recent_submission_timestamp,
    load_submission_token,
    report_lifecycle_alert,
    run_app_review_config_sweep,
    submit_review_version,
)
from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.other.endpoints import rate_limit_dependency

router = APIRouter()
_VERSION_PATTERN = re.compile(r'^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$')
_VERSION_CODE_PATTERN = re.compile(r'^[1-9][0-9]{0,9}$')


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')

    platform: Literal['ios', 'android']
    version: str = Field(min_length=5, max_length=32)
    version_code: str | None = Field(default=None, min_length=1, max_length=10)
    submitted_at: datetime

    @model_validator(mode='after')
    def validate_identity(self) -> 'ReviewSubmission':
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise ValueError('version must be X.Y.Z')
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must include a timezone")
        if self.platform == 'android':
            if self.version_code is None or not _VERSION_CODE_PATTERN.fullmatch(self.version_code):
                raise ValueError('Android submission requires a positive numeric version_code')
        elif self.version_code is not None:
            raise ValueError('version_code is only valid for Android submissions')
        return self


@router.post(
    '/v2/internal/app-review-config/submissions',
    include_in_schema=False,
    dependencies=[
        Depends(
            rate_limit_dependency(
                "app_review_config_submission",
                requests_per_window=10,
                window_seconds=60,
            )
        )
    ],
)
def record_review_submission(
    body: ReviewSubmission,
    submission_token: str | None = Header(default=None, alias='X-Review-Config-Token'),
):
    try:
        expected = load_submission_token()
    except StoreCredentialsUnavailable:
        report_lifecycle_alert(
            body.platform,
            'submission_token_unavailable',
            'Codemagic submission receipt cannot be authenticated',
        )
        # Use the same response for a missing secret and a bad token so this
        # endpoint does not disclose whether the Secret Manager value exists.
        raise HTTPException(status_code=401, detail="invalid submission token") from None
    supplied = submission_token.encode("utf-8") if submission_token is not None else b""
    if not supplied or not hmac.compare_digest(supplied, expected.encode("utf-8")):
        report_lifecycle_alert(
            body.platform,
            'submission_token_rejected',
            'Codemagic submission receipt token was rejected',
        )
        raise HTTPException(status_code=401, detail='invalid submission token')
    if not is_recent_submission_timestamp(body.submitted_at):
        raise HTTPException(status_code=409, detail="submission receipt is stale")
    try:
        return submit_review_version(body.platform, body.version, body.version_code)
    except SubmissionConfigConflict:
        raise HTTPException(status_code=409, detail="submission lease changed; retry receipt") from None


@router.post('/v2/app-review-config/sweep', include_in_schema=False)
@read_origin('job:app_review_config_sweep')
def sweep_app_review_config(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    return run_app_review_config_sweep()
