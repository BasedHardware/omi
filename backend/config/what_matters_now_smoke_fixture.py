"""Code-owned identity and runtime gate for the development What Matters Now smoke."""

import os

from config.canonical_memory_cohort import DEV_WHAT_MATTERS_NOW_SMOKE_UID

WHAT_MATTERS_NOW_SMOKE_UID = DEV_WHAT_MATTERS_NOW_SMOKE_UID


def is_development_smoke_fixture(uid: str, *, stage: str | None = None) -> bool:
    """Return whether ``uid`` is the one fixture allowed by an explicit dev runtime."""

    runtime_stage = os.getenv('OMI_ENV_STAGE') if stage is None else stage
    return runtime_stage == 'dev' and uid == WHAT_MATTERS_NOW_SMOKE_UID


__all__ = ['WHAT_MATTERS_NOW_SMOKE_UID', 'is_development_smoke_fixture']
