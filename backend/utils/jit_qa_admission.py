"""Fail-closed user admission for the isolated JIT QA Cloud Run plane.

The QA services use a public Cloud Run transport so Firebase bearer tokens can
reach the application.  That transport setting is not an account boundary:
without this check any valid Omi token could reach a dev data plane and a
billable model route.  The check is inert unless the deployment explicitly
sets the QA-only switches, so normal services keep their existing policy.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

QA_UID_ALLOWLIST_ENV = "OMI_JIT_QA_UID_ALLOWLIST"
QA_AUTH_ONLY_ENV = "OMI_JIT_QA_AUTH_ONLY"
QA_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
QA_STAGE_ENV = "OMI_ENV_STAGE"
QA_PROJECT = "based-hardware-dev"


class JITQAAdmissionError(ValueError):
    """The request is outside the explicitly configured QA identity."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def jit_qa_auth_only_enabled(environ: Mapping[str, str] | None = None) -> bool:
    values = os.environ if environ is None else environ
    return _truthy(values.get(QA_AUTH_ONLY_ENV))


def enforce_jit_qa_uid(uid: str, environ: Mapping[str, str] | None = None) -> None:
    """Reject every authenticated UID except the exact isolated QA UID.

    The deployment must identify both the development stage and project.  This
    prevents a copied QA switch from accidentally narrowing a production
    service, while a missing/invalid allowlist fails closed when the switch is
    on.
    """

    values = os.environ if environ is None else environ
    if not _truthy(values.get(QA_AUTH_ONLY_ENV)):
        return
    # Keep this normalization aligned with the Firebase verify-only fence and
    # Firestore client fence.  Cloud Run env values can carry whitespace from
    # generated manifests, while stage names are case-insensitive.
    stage = (values.get(QA_STAGE_ENV) or "").strip().casefold()
    project = (values.get(QA_PROJECT_ENV) or "").strip()
    if stage != "dev" or project != QA_PROJECT:
        raise JITQAAdmissionError("JIT QA auth-only mode requires the based-hardware-dev dev project")
    allowed = tuple(item.strip() for item in values.get(QA_UID_ALLOWLIST_ENV, "").split(",") if item.strip())
    if len(allowed) != 1 or "/" in allowed[0]:
        raise JITQAAdmissionError("JIT QA auth-only mode requires exactly one UID")
    if uid != allowed[0]:
        raise JITQAAdmissionError("authenticated UID is outside the isolated JIT QA allowlist")


__all__ = [
    "JITQAAdmissionError",
    "QA_AUTH_ONLY_ENV",
    "QA_PROJECT",
    "QA_PROJECT_ENV",
    "QA_STAGE_ENV",
    "QA_UID_ALLOWLIST_ENV",
    "enforce_jit_qa_uid",
    "jit_qa_auth_only_enabled",
]
