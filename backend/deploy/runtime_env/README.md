# Backend runtime manifest versions

Edit `_base.yaml` and the environment overlays, then regenerate
`backend/deploy/runtime_env.yaml` with `backend/deploy/compose_runtime_env.py`.

Version 2 requires the backend voice route's staging bucket as an explicit
literal: `syncing-local-development` in dev and `syncing-local` in prod. Normal
admission and the existing prebuild preflight reject missing, blank, implicit,
or wrong-environment bindings.

Historical version 1 releases inherited this binding from Cloud Run. Current
controls must still replay those admitted releases during rollback.
`backend/scripts/runtime_env_compat.py` materializes the reviewed literal only
when that version's binding is missing. Explicit invalid bindings remain
invalid. The renderer and validator share this migration; it neither changes
the source document nor requires an operator bypass. Unknown versions fail.

The captured voice-storage projection of production source `8ad1d75cc9df`
and the real prebuild entry point are covered by
`backend/tests/unit/test_runtime_env_manifest_compat.py`.
