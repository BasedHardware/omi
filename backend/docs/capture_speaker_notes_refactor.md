# Capture, speaker and notes refactor: contracts

Program: one authority per decision. Each new path ships behind a mode flag read by
`config/refactor_modes.py` (`off` | `shadow` | `serve`, default `shadow`), bakes in prod,
and the old path is deleted in a follow-up PR after the bake.

| Contract | Module | Producer | Consumers |
|---|---|---|---|
| Rollout modes and boolean switches | `config/refactor_modes.py` | all lanes | all lanes |
| Capture coverage ledger | `models/capture_coverage.py` | L1 coverage (sync, batch, query endpoint) | L4 listen (records live ranges, emits `capture_committed`), L5 clients |
| Speaker evidence | `models/speaker_evidence.py` | L2 speaker identity service | L3 notes and episodes, L4 lifecycle, L5 clients |
| Boundary evidence | `models/boundary_evidence.py` | L5 desktop, calendar and screen integrations | L4 conversation and episode boundaries |
| Episode moment rendering | `utils/episodes/moment_render.py` | L3 | L4 (`utils/episodes/service.py`) |

Mode flags: `CAPTURE_COVERAGE_MODE`, `SPEAKER_EVIDENCE_MODE`, `NOTES_PACKET_V2_MODE`,
`EPISODE_BOUNDARIES_MODE`, `LIFECYCLE_V2_MODE`. The serve cohort uses
`<FLAG>_SERVE_PERCENT` and `<FLAG>_SERVE_UID_SHA256S` (digests only; never a raw uid).
