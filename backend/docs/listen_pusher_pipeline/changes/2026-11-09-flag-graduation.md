# 2026-11-09 production flag graduation

David accepted all seven flag-rulings cards on 2026-11-09. This change uses only
`graduate-list.json` from the dated flag-decisions docket; its recorded production
snapshot was read at 03:20Z. No live flags or customer data were accessed.

Seventeen listed controls are removed. Audio archive coalescing, notes-agent
cohort admission, Episodes admission for beta and store, mobile/auto-language
server batch selection, speaker-score snapshots, cost routing at 100 percent,
first-summary deadline admission, sync status reconciliation, sync assignment
contention retries, and legacy completion convergence retain their recorded
production behavior. Paid mobile visible restore remains disabled and its code
is removed. Empty explicit-app reprocess retains the generic processing failure.
The Episodes cohort allowlist is redundant at 100 percent and retired with its
percentage. The notes-agent allowlist remains owned by the separate retirement lane. Other kill, health, privacy, client-capability,
consent, custody and stage gates remain authoritative.

The [pipeline contract](../../listen_pusher_pipeline.mdx) describes the resulting
behavior. Scoped pipeline budget slots fall from 165 to 161, with the four
removed names moved to the append-only retired ledger. Graduated registry entries
move to `retired`, preventing reads or declarations from being reintroduced.

## Mixed-service controls retained for review on 2026-11-23

The shared `main.py` mounts through `app_roles.py`; `routers.transcribe`, including
`/v4/listen`, belongs to the API and realtime roles. The serving manifests do not
set `OMI_ROLE`, so its default `all` mounts it for Cloud Run services as well as
the GKE listener. `test_backend_runtime_env_validator.py` also documents the four
Cloud Run copies as serving capture, sync, developer processing and reprocess.
The docket assigns false to Cloud Run and true to listener/pusher for four of
these controls. These are reachable readers, so neither value can be made
universal while preserving the supplied production configuration.

| Control | Reader trace |
| --- | --- |
| `LIVE_CAPTURE_WINDOW_MERGE_UNION` | `utils/manual_speaker_assignments.py` and `utils/audio_timeline.py`, plus live capture merges; both REST and live routes read it. |
| `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS` | Listen receiver constructs `utils/stt/live_session.py`; that and `utils/stt/replay_capture_accounting.py` read the control. |
| `SONIOX_WIRE_LEDGER` | `utils/stt/soniox.py` and `utils/stt/live_session.py`, reached from `routers/listen/receiver.py` on the shared backend. |
| `SONIOX_CAPTURE_AXIS_DIAGNOSTICS` | `utils/stt/soniox_capture_axis.py`, called by both the raw Soniox socket and shared live-session wrapper. |
| `FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED` | `config/summary_guarantee.py` is consumed by `utils/enrichment/outbox.py` and `utils/enrichment/consumer.py` across processing hosts; the docket splits backend/listen from sync/integration. |

All five retain their code and deployment wiring, with a dated deferral on their
own registry rows. The independent registry-only and retirement dockets are
untouched. The lead must include this deferral in the combined PR body.

Rollback is a source revert. This commit performs no runtime rollout and does not
change production flags. There is no percentage ramp for permanent behavior.
