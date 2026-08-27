"""Whether screen-frame egress may run at all, checked before anything leaves the box.

The pipeline is `canonicalize -> judge -> mint approval -> write`. The judge is
the first step that sends a user's screen bytes off Omi's infrastructure (to
Gemini), and it runs two stages before anything looks at `BUCKET_SCREEN_FRAMES`
or the approval signer. So "the bucket is not provisioned yet" is not an off
switch for this feature: without a gate above the judge, merging it means every
Rewind user's candidate frames are uploaded and judged, and only then does the
request fail — bytes spent, screens seen, nothing stored.

This module is that gate. It is deliberately three independent conditions,
all of which must hold, because each protects a different failure:

- `SCREEN_FRAME_EGRESS_ENABLED` must be exactly "true". An explicit, default-off
  flag means provisioning the bucket does not silently turn the feature on for
  everyone the moment infrastructure lands. Turning it on stays a deliberate act.
- `BUCKET_SCREEN_FRAMES` must be set. Judging a frame that provably cannot be
  stored is pure cost and pure exposure.
- A signer must be configured (`SCREEN_FRAME_KMS_KEY` or
  `SCREEN_FRAME_SIGNING_SECRET`). Without one, `build_approval_claims` raises
  after the judge has already run.

Read from the environment on every call rather than at import: the routers are
long-lived, and tests set these per-case.
"""

from __future__ import annotations

import os


def _present(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def screen_frame_egress_enabled() -> bool:
    """True only when egress is explicitly enabled AND fully provisioned."""
    if (os.getenv("SCREEN_FRAME_EGRESS_ENABLED") or "").strip().lower() != "true":
        return False
    if not _present("BUCKET_SCREEN_FRAMES"):
        return False
    return _present("SCREEN_FRAME_KMS_KEY") or _present("SCREEN_FRAME_SIGNING_SECRET")
