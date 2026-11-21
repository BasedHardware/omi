# 2026-11-21 Confirm the continuation pointer before sealing v3 rotation

Long v3 recording rotation keeps the previous conversation active until Firestore confirms the
origin's continuation pointer names the prepared successor. A failed pointer transaction is
retried and read back. If the outcome remains unknown, rotation backs off and retains the
candidate instead of sealing the previous row or deleting a possible pointer target.

## Rollout and rollback

This changes no runtime flag or serving configuration. Keep rotation off while the fix is shipped
to backend-listen and until Release and David approve a target scope. Follow the canary and audio
custody gates in SCA-3416 before expanding. Revert the code change to roll back.

## Verification

`tests/unit/test_listen_v3_rotation_continuation.py` covers a pointer write/readback outage and an
ambiguous committed write. Both paths require durable pointer confirmation before the old row
can seal.

[Recording-derived conversations V3](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
