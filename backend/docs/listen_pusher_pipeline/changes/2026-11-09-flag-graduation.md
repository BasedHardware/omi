# 2026-11-09 production flag graduation

David accepted all seven flag-rulings cards on 2026-11-09. This change uses only
`graduate-list.json` from the dated flag-decisions docket; its recorded production
snapshot was read at 03:20Z. No live flags or customer data were accessed.

Eight listed controls are removed: `AUDIO_ARCHIVE_COALESCE_ENABLED`,
`CONVERSATION_NOTES_AGENT_PERCENT`, `EPISODES_PERCENT`,
`SERVER_BATCH_ONLY_VISIBLE_RESTORE_PERCENT`, `SPEAKER_MATCH_SCORES_ENABLED`,
`CONVERSATION_REPROCESS_RESULT_CONTRACT_ENABLED`,
`FIRST_SUMMARY_DEADLINE_ENABLED`, and `FIRST_SUMMARY_DEADLINE_PERCENT`. Paid mobile visible restore remains disabled
and its code is removed. Empty explicit-app reprocess retains the generic
processing failure. The Episodes cohort allowlist `EPISODES_UID_ALLOWLIST` is
redundant at 100 percent and retired with its percentage. The notes-agent allowlist
remains owned by the separate retirement lane. Other kill, health, privacy,
client-capability, consent, custody and stage gates remain authoritative.

The [pipeline contract](../../listen_pusher_pipeline.mdx) describes the resulting
behavior. None of the graduated controls is in the pipeline flag ledger, so
`flag_budget.json` is unchanged (268 names, 165 slots).
Graduated feature-registry entries move to `retired`, preventing their reads or
declarations from being reintroduced.

## Nine graduations deferred after service-scope review

David's 2026-11-09 ruling is to retain a flag whenever graduation would widen its
behavior beyond the recorded production scope. These nine controls retain main's
env readers, gates, manifests, tests and registry metadata. Their registry notes
record the deferral; review dates, ramp deadlines and extensions are unchanged.

| Control | Recorded production scope | Why graduation is deferred |
| --- | --- | --- |
| `SERVER_BATCH_ONLY_MOBILE_PERCENT` | `prod-omi-backend-listen` | Permanent 100% selection would also admit mobile capture on the Cloud Run copies. |
| `SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT` | `prod-omi-backend-listen` | Permanent auto-language selection would also admit mobile/web capture on the Cloud Run copies. |
| `STT_ROUTING_MODE` | `prod-omi-backend-listen` | Permanent routing would activate shared listen routes and routing health work outside the listener. |
| `STT_ROUTING_ON_PERCENT` | `prod-omi-backend-listen` | Universal routing admission would remove the separate service cohorts. |
| `REVIEW_SURFACE_MODE` | `prod-omi-backend-listen`, `run:backend`, `run:backend-sync`, `run:backend-sync-backfill` | Removing route and storage guards would enable Review on `run:backend-integration`. |
| `SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED` | `run:backend-integration`, `run:backend-sync`, `run:backend-sync-backfill` | Always retrying would change the listener's late-audio sync-assignment path. |
| `EPISODES_CLIENT_CHANNELS` | `run:backend` (`beta,store`) | The Episodes router mounts on every role; admitting store unconditionally would let store clients set the capable-client marker on other copies, including the listener and integration service. |
| `SYNC_LEGACY_COMPLETION_CONVERGENCE` | `run:backend-sync`, `run:backend-sync-backfill` | A stage-only policy would enable under-lock convergence on every production-stage copy that mounts the sync router. |
| `SYNC_DURABLE_STATUS_RECONCILIATION` | `run:backend` | Removing the guard would add durable Firestore status reads on every copy that serves the sync polling route. |

The shared `main.py` mounts through `app_roles.py`; `routers.transcribe`, including
`/v4/listen`, belongs to the API and realtime roles. The serving manifests do not
set `OMI_ROLE`, so its default `all` mounts it for Cloud Run services as well as
the GKE listener. A universal default would therefore change reachable readers
outside the supplied production snapshot.

## Five existing mixed-service deferrals retained

| Control | Reader trace |
| --- | --- |
| `LIVE_CAPTURE_WINDOW_MERGE_UNION` | `utils/manual_speaker_assignments.py` and `utils/audio_timeline.py`, plus live capture merges; both REST and live routes read it. |
| `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS` | Listen receiver constructs `utils/stt/live_session.py`; that and `utils/stt/replay_capture_accounting.py` read the control. |
| `SONIOX_WIRE_LEDGER` | `utils/stt/soniox.py` and `utils/stt/live_session.py`, reached from `routers/listen/receiver.py` on the shared backend. |
| `SONIOX_CAPTURE_AXIS_DIAGNOSTICS` | `utils/stt/soniox_capture_axis.py`, called by both the raw Soniox socket and shared live-session wrapper. |
| `FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED` | `config/summary_guarantee.py` is consumed by `utils/enrichment/outbox.py` and `utils/enrichment/consumer.py` across processing hosts; the docket splits backend/listen from sync/integration. |

All five retain their code and deployment wiring, with a dated deferral on their
own registry rows (review by 2026-11-22, the end of each row's bounded extension). Their decision and terminal fields retain main's pending and
undecided values, rather than claiming graduation. The independent registry-only
and retirement dockets are untouched.

Rollback is a source revert. This commit performs no runtime rollout and does not
change production flags. There is no percentage ramp for permanent behavior.

## Product invariants affected

- INV-MEM-4
- INV-TASK-2

Graduating notes admission preserves the existing canonical-memory promotion
authority and task-capture policy. Restoring service-scoped controls preserves
those same authorities on hosts outside the recorded production scope.

## Local validation (2026-11-09)

Reported verification processes explicitly cleared ambient `GOOGLE_APPLICATION_CREDENTIALS` or `CLOUDSDK_*`
variables. Backend pytest files ran in separate processes under the workspace
`bin/omi-heavy` gate, using this worktree's Python 3.11 virtual environment.
No Omi production reads, writes, runtime rollout, or GCP credential tier were used.

- `python scripts/check_feature_flag_registry.py`: OK.
- `python -m pytest -q scripts/test_check_feature_flag_registry.py`: 109 passed.
- `cd backend && python -m pytest -q <file>` for each file below: 2,158 passed across 51 files; no skips or failures.

| Backend test file | Passed |
| --- | ---: |
| `tests/unit/test_agent_transcript_overlay.py` | 13 |
| `tests/unit/test_backend_listen_helm_defaults.py` | 13 |
| `tests/unit/test_backend_runtime_env_validator.py` | 206 |
| `tests/unit/test_batch_pipeline_projection.py` | 64 |
| `tests/unit/test_batch_pipeline_quarantine.py` | 26 |
| `tests/unit/test_batch_pipeline_quarantine_recovery.py` | 163 |
| `tests/unit/test_batch_stage_policy.py` | 18 |
| `tests/unit/test_desktop_batch_only.py` | 82 |
| `tests/unit/test_dream_admission_contention.py` | 7 |
| `tests/unit/test_dream_budget_settlement.py` | 16 |
| `tests/unit/test_dream_canary.py` | 12 |
| `tests/unit/test_dream_cleanup_edits.py` | 45 |
| `tests/unit/test_dream_lease_reclamation.py` | 23 |
| `tests/unit/test_dream_queue.py` | 21 |
| `tests/unit/test_dream_review_round_two.py` | 15 |
| `tests/unit/test_flag_budget.py` | 24 |
| `tests/unit/test_graduated_flag_behavior.py` | 5 |
| `tests/unit/test_listen_policy_runtime.py` | 5 |
| `tests/unit/test_listen_session_policy.py` | 78 |
| `tests/unit/test_live_chain_exhaustion_classification.py` | 10 |
| `tests/unit/test_live_cost_reset_fencing.py` | 14 |
| `tests/unit/test_live_cost_router.py` | 138 |
| `tests/unit/test_live_death_socket_accounting.py` | 34 |
| `tests/unit/test_live_evidence_settlement.py` | 44 |
| `tests/unit/test_live_recovery_matrix.py` | 106 |
| `tests/unit/test_live_replay_provider_pairs.py` | 31 |
| `tests/unit/test_live_router_cache_isolation.py` | 10 |
| `tests/unit/test_live_router_hardening.py` | 158 |
| `tests/unit/test_live_router_readiness.py` | 62 |
| `tests/unit/test_live_routing_health.py` | 24 |
| `tests/unit/test_live_session_transcript_outcome.py` | 25 |
| `tests/unit/test_live_stt_chain.py` | 79 |
| `tests/unit/test_live_stt_fleet_health_write_metrics.py` | 12 |
| `tests/unit/test_live_stt_restart_burst_sim.py` | 31 |
| `tests/unit/test_modulate_capacity_failover.py` | 22 |
| `tests/unit/test_modulate_live_withdrawal.py` | 12 |
| `tests/unit/test_open_loops_review_routes.py` | 32 |
| `tests/unit/test_parakeet_failover_exhausted.py` | 22 |
| `tests/unit/test_review_spelling_context.py` | 24 |
| `tests/unit/test_review_stale_answers.py` | 51 |
| `tests/unit/test_server_batch_auto_language.py` | 42 |
| `tests/unit/test_server_batch_unsupported_languages.py` | 48 |
| `tests/unit/test_server_batch_web.py` | 17 |
| `tests/unit/test_soniox_capture_axis_r10.py` | 23 |
| `tests/unit/test_soniox_idle_close.py` | 98 |
| `tests/unit/test_soniox_idle_cost_reselect.py` | 19 |
| `tests/unit/test_soniox_rate_limit.py` | 12 |
| `tests/unit/test_stt_failover_recovery_flag.py` | 45 |
| `tests/unit/test_stt_routing_cohort.py` | 27 |
| `tests/unit/test_sync_assignment_contention_retry.py` | 19 |
| `tests/unit/test_verify_pusher_config_references.py` | 31 |


The initial runtime-env validator run hit a 180-second runner limit. The full
rerun passed with a 900-second per-file limit. The first executing preflight hit
the Firestore query-shape suite's 300-second wall limit; the unchanged check
passed with `BACKEND_UNIT_FILE_BUDGET_SECONDS=900`. No assertion or registry
checker was weakened.

Additional repository preflight status: **incomplete**. `make preflight` ran
with the larger wall allowance; 43 manifest checks passed. It stopped on missing
local PR invariant citations and its tracked-file mutation guard detected the
cosmetic hintable-reader hunk finalized during that run. The citations are now
included above. Two checks were cancelled and ten had not started after fail-fast.
Follow-up manifest runs waited nearly an hour for `omi-heavy` admission and were
cancelled by their exact owned PIDs; they did not run. No checks were disabled.

Remaining checks to complete before publication:

- `product-invariants`
- `desktop-changelog-data`
- `backend-workflow-contracts`
- `backend-runtime-env-compose`
- `desktop-backend-release-boundary`
- `git-author-identity`
- `mobile-changelog-data`
- `mobile-client-compat-catalog`
- `public-build-contract`
- `pusher-dev-bake-observability`
- `pusher-rollout-quality-gate`
- `shared-config-migration-preflight`
- `task-capture-authority`

Rerun with the local draft metadata and the same wall allowance when host capacity
is available (after clearing the cloud credential variables described above):

```bash
BACKEND_UNIT_FILE_BUDGET_SECONDS=900 \
OMI_PR_BODY_FILE=backend/docs/listen_pusher_pipeline/changes/2026-11-09-flag-graduation.md \
/Users/dazheng/workspace/omi/bin/omi-heavy run --wait 3600 -- make preflight
```


Rollback remains a source revert; this is a local commit only.
