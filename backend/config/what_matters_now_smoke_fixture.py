"""Code-owned identity and runtime gate for the development What Matters Now smoke."""

import os

WHAT_MATTERS_NOW_SMOKE_UID = 'omi-dev-what-matters-now-smoke-v1'


def is_development_smoke_fixture(uid: str, *, stage: str | None = None) -> bool:
    """Return whether ``uid`` is the one fixture allowed by an explicit dev runtime."""

    runtime_stage = os.getenv('OMI_ENV_STAGE') if stage is None else stage
    return runtime_stage == 'dev' and uid == WHAT_MATTERS_NOW_SMOKE_UID


__all__ = ['WHAT_MATTERS_NOW_SMOKE_UID', 'is_development_smoke_fixture']
