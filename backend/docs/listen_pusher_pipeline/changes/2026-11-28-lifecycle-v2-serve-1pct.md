# Lifecycle v2 serves 1% of production accounts

**What changed:** production now binds `LIFECYCLE_V2_MODE=shadow` and `LIFECYCLE_V2_MODE_SERVE_PERCENT=1` on all six readers: the backend, backend-sync, backend-sync-backfill and backend-integration Cloud Run services, plus GKE backend-listen and pusher. Dev is unchanged. Before this, the key was unbound everywhere and the default `shadow` applied with no cohort. Contract: [Conversation Lifecycle](../../listen_pusher_pipeline.mdx#2-conversation-lifecycle-silence-timeout-path).

**Why:** David ruled on 2026-11-28 to ramp lifecycle v2 to serve: 1% → 10% → 100% by 2026-12-12, with Release expanding each step. The plan and its gates are on SCA-5312. Over the 7 days before this change, `omi_lifecycle_refactor_shadow_total` recorded no error outcome.

**What the 1% cohort gets:**
- The quiet-close and recovery clock uses `last_speech_at`.
- Listen stops the per-batch `finished_at` write when segments are present.
- Search re-indexes on the status change.
- Empty live rows keep their quiet-check obligation.
- Episode moments use the user's output language.
- Post-processing runs on bounded `postprocess_v2` and `episode` pools.
- Stale recovery reads the head on every third page.

**Fleet-wide side effect:** any configured cohort withholds the `finjob_candidate_queries` pushdown for the 2-hour status-only sweep. That sweep is capped at 2,000 rows per tick with a 5-minute cooldown, so the worst case is 576k reads/day.

**Rollback:** set `LIFECYCLE_V2_MODE_SERVE_PERCENT` to `'0'` in `backend/deploy/runtime_env/prod.overlay.yaml` and in both prod chart values files, then recompose. This returns the cohort to pure shadow, and nothing needs to be undone.

**Readback:** posted on SCA-5312 once all six serving revisions carry the binding, after a 24-hour hold.
