# Legacy deletion map (batch record lane ramp)

As of 2026-10-25 (`origin/main` b921ae2). Review by 2026-11-01 or at the 100%
step. Owners are lanes or roles. Gates use the [trip set](../utils/batch_pipeline/CONTRACT.md#trips-which-invariant-each-enforces);
rulings are in [adr/](adr/README.md). Sources: the 2026-10-25 pipeline
architecture review (sections 05–07), the batch stepback gate table, and the
acceleration consult §1 (CR-1), all in the rollout records.

**Rule.** Code is deleted only when no cohort can reach it. Until then a legacy
path is retired *per cohort* by config, and the rollback is a config write, not a
revert. Deletion is the cheapest quality gain available, so each row below has an
owner and a gate rather than waiting for a cleanup sprint.

## Per cohort, at every step (CR-1)

At 5%, 10%, 25% and 50%, the cohort batch admits stops using legacy sync for its
uploads, in lockstep with admission (proposed 10-24 in the acceleration consult;
not yet ratified as an ADR).

| What retires | Gate | Owner | Rollback |
| --- | --- | --- | --- |
| Legacy sync admission for the batch-admitted cohort (`utils/sync/legacy_dark.py:legacy_admission_allowed`) | That step's T1–T5 clean for its full hold; per-cohort WAL/custody coverage; a speaker-parity sample for the cohort | CR-1 lane (mission-critical routing) | Legacy admission back on for the cohort |

UNVERIFIED: a per-cohort legacy switch does not exist on main. `legacy_sync_mode`
(`utils/rollout/runtime_percent.py`) is one value per environment, and
[legacy-dark.md](runbooks/legacy-dark.md) allows `on → draining` only at batch
100%. CR-1 at partial percents needs a cohort-scoped switch first.

## At 50%

| What becomes deletable | Gate | Owner | Rollback |
| --- | --- | --- | --- |
| Single-vendor language-ID dependency in batch routing (`utils/stt/batch_language.py:detect` probe as the only route) | Self-LID #23460 merged, co-deployed CPU + GPU, LID agreement ≥ 99.9% in a staging multilingual soak | batch quality lane | Self-LID kill switch; the vendor probe stays as fallback until 100% |

## At 100%, then one clean week

| What becomes deletable | Gate | Owner | Rollback |
| --- | --- | --- | --- |
| Legacy sync lane: mode `on → draining → dark` | The `DRAINING_PRECONDITIONS` in [legacy-dark.md](runbooks/legacy-dark.md); G2 in-cluster guard live | lead (applies); sync lane | One write back to `on` |
| Legacy transcription branch of `routers/sync.py:sync_local_files_v2`, and the legacy Cloud Tasks job `routers/sync.py:_run_sync_job_attempt` | Mode `dark` for 7 days; drain census (`scripts/legacy_dark/drain_census.py`) at 0 pending legacy jobs; no T1/T2 trip in that week | sync lane | Revert the deletion PR (mode stays `dark`) |
| Deprecated v1 handler `routers/sync.py:sync_local_files` | Zero v1 requests for 14 days (UNVERIFIED: no per-route v1 counter confirmed) | sync lane | Revert |
| Stage C per-clip diarization: `utils/stt/diarization.py` `/v2/diarization` client and `diarizer/api_v2.py` route | Diarization on the recovery path (the audio that must stay on the vendor gets pyannote speakers); one diarization service | batch quality lane | Revert; the RPC is stateless |
| One of three speaker resolvers: `utils/stt/conversation_speakers.py:resolve_conversation_speakers`, `utils/conversations/speaker_resolution.py:_resolve`, `routers/listen/speakers.py:_match_unmapped` | #23581 merged; named-speaker share on the batch cohort ≥ legacy for 7 days. UNVERIFIED which resolver goes | batch speakers lane | Revert |
| Legacy-mode fence: `utils/rollout/runtime_percent.py:legacy_sync_mode`, the double-processing fence in `utils/sync/legacy_dark.py` | All legacy code above deleted | sync lane | Revert |
| Optional legacy fresh lane `utils/sync/legacy_fresh.py` (`SYNC_LEGACY_FRESH_*`) | Mode `dark`; no legacy fresh admissions for 7 days | sync lane | Revert |
| Graduated batch flags (e.g. `BATCH_PIPELINE_SERVING_ENABLED`, cohort percents at 100) | Flag at its terminal value for 7 days; row marked `terminal: on` in `config/feature-flags.yaml` | each flag's owner | Revert; lower `config/flag_budget.json` in the same change ([ADR 0006](adr/0006-pipeline-flag-budget.md)) |

## Not on the batch ladder

| Path | Gate | Owner |
| --- | --- | --- |
| Legacy live failover chain `utils/stt/streaming.py:connect_stt_socket_with_fallback` (callers: `routers/listen/receiver.py`, `routers/chat.py`, `utils/stt/live_session.py`) | `utils/stt/live_chain.py:connect_configured_chain` serves 100% of listen and chat for 7 days; callers migrated | live STT lane |

Deleting a row means: the deletion PR cites this file, removes the row, and
lowers the flag budget for any env names it removes.
