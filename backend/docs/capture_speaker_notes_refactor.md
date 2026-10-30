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

## Integrated seams

`backend/app_roles.py` mounts authenticated capture-boundary intake alongside episodes;
the sync router serves `GET /v2/capture-coverage`. Both routes are in the route policy
manifest and app-client OpenAPI. Coverage queries pair bounded repeated `start` and
`end` parameters with the full capture key. Channel, epoch string, device and recording
session must agree across live receipt, ledger query and backup upload. A missing
optional key component is a distinct partition, never a wildcard.

Live transcript durability precedes L1 ledger recording and `capture_committed`.
L5's from-segments adapter consumes the real L1 authority. A complete covered range
can return its existing conversation receipt; a partially covered segment without
word/frame alignment retains audio and refuses serving admission. Shadow preserves
legacy output. Open-live discovery includes same-key hints without a device, reads
only bounded metadata, and revalidates the full row in the assignment transaction.

The live speaker emitter carries additive `is_user` for proposals and retractions,
retaining the older owner sentinel. L2's policy is also the source of continuity and
GPU clustering thresholds; the GPU image copies it under `omi_speaker_policy` to
avoid NeMo's top-level `utils` package. Boundary rosters contribute low-prior,
non-label-eligible candidates. They never establish voice identity.

Episode moments pass account and conversation identity to L3's renderer and pass
conversation language to incremental updates. The L4 invoke adapter resolves output
language through L3's authority. Notes dedupe hashes packet/output/language source
modules, effective serving selection and packet version, so cohort or module changes
cannot reuse a legacy success checkpoint. Shadow does not add a model call.

## Durable lifecycle and deletion

Serving merge admission claims every source and creates `kind=conversation_merge`
in `conversation_finalization_jobs` atomically. A renewable epoch-fenced lease owns
preparation. The correction-anchor transfer transaction also seals `source_cleanup`
on that job. An expired pre-transfer job retracts its provisional target before
restoring exactly its source bindings. A sealed job requeues only idempotent source
cleanup through the existing protected worker, without another notes call. Cleanup
has five attempts; persistent failure retains the survivor and a durable dead letter.
Recovery continues after the lifecycle mode is turned off.

Quiet deadlines and recovery admission use the same serve-gated speech clock.
An empty, expired, past-deadline check creates an `empty_ready` obligation. Its
successor stays durable until `lifecycle.delete_empty_recording_conversation`
succeeds. The deletion transaction rereads content, session identity and the lease;
a reconnect or late content write prevents deletion. Empty rows never enter paid
processing through this path.

User deletion records its tombstone before purging all 128 bounded continuation
chunk documents, including when the parent conversation is absent. Staging stores
an encrypted payload and a seven-day `expires_at`; expired parts cannot assemble a
conversation and a retry replaces an expired index. Physical expiry requires the
Firestore TTL policy for collection group `from_segments_chunks`, field `expires_at`
to be enabled before the continuation cohort serves. This source integration does
not apply a database policy or change a runtime cohort. Account erasure also reaches
the staging collection directly.

## Default and rollout contract

All backend refactor modes remain `shadow`, percentage cohorts remain zero and
digest cohorts remain empty unless configured at runtime. Client serving flags are
false/unknown; custody release requires an explicit true opt-in. No serving cohort
is set in a manifest. Rollback disables new admission, while durable lifecycle jobs
continue reconciling. Runtime TTL activation, PostHog row configuration and cohort
expansion are separate operator work.

The reviewed TTL declaration is `backend/deploy/from-segments-retention.json`.
A credential-free plan is available with:

```sh
python backend/scripts/batch_pipeline_ttl.py --project demo-refactor-integration \
  --policy backend/deploy/from-segments-retention.json
```

The default CLI policy remains the existing batch-completion policy; explicitly
select the staging declaration for its separately authorized apply.
