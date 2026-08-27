# Context Director — architecture

The Windows port of macOS's context-bucket proactivity system: durable context
buckets built from screen activity, a director LLM pass that decides when an
interruption adds value, strict grounding so a notification can never outrun
its evidence, and the legacy TCRS resurfacing path for the flag-off world.
Every behavioral rule is ported rule-for-rule from the macOS Swift sources;
the ground-truth extraction lives in
`desktop/windows/docs/mac-parity-audit/track3-ground-truth/gt-context-director-build.md`.

## Data flow (pipeline on: `contextDirectorEnabled`)

```
coordinator frame loop (core/coordinator.ts)
  └─ directorAssistant.ts (peer: tracks frames; onContextSwitch = the trigger)
       ├─ visitCoordinator.ts  — serialized visit open/close (1s dwell rule)
       │    └─ ipc/contextBucketStore.ts — visits/buckets/facts/versions (SQLite)
       ├─ service.runDepartureExtraction — extraction lane call per qualified
       │    departure → writeExtraction → publishVersion → destination apply
       └─ engine.ts contextEntered(fence)
            ├─ prompts.ts     — stable (cache-prefix) + volatile prompts
            ├─ laneClient.ts  — POST {desktopApiBase}/v1/desktop/proactivity/completions
            ├─ retrieval.ts   — at most one bounded hop (3 tool searches)
            ├─ ipc/proactivityLedger.ts — reservation → terminal row (budget)
            └─ present via core/notify.notifyProactive('director', …)
```

## Data flow (pipeline off: the TCRS legacy path)

```
directorAssistant.onContextSwitch (titled, privacy-allowed)
  └─ tcrs.ts appWindowEvent → subjectBinding.resolve → tcrs.observe
       └─ 2s debounce → contextMatches → material hint (5-min dedupe)
            → control gate → PUT context-snapshot → POST what-matters-now/evaluate
            → 'intelligence:contextProjection' push
                 → renderer lib/intelligence/contextProjectionHost.ts
                      → dashboardStore.applyContextProjection
```

## Module map

| Module | Mac source | Role |
|---|---|---|
| `titleNormalizer.ts` | ContextTitleNormalizer | identity-defining title rules |
| `destinationKey.ts` | ContextDestinationKey | browser-tab collapse sanitizer + prompt fragment |
| `workHandles.ts` | WorkHistoryHandle | durable url/file identity + canonicalization |
| `visitCoordinator.ts` | ContextVisitCoordinator | serialized visit state machine, GC cadence |
| `prompts.ts` | ContextProactivityPromptBuilder + assembler | byte-exact prompt surface, schemas, clamps |
| `laneClient.ts` | ProactiveLaneClient | proactivity-lane transport, 429 cooldowns |
| `retrieval.ts` | ContextDirectorRetrieval | hop admission, fail-closed mapping, chunk-wins merge |
| `engine.ts` | ContextProactivityEngine | trigger order, grounding, hop, candidate fast path |
| `deliveryPolicy.ts` | ContextDeliveryAuthority (gate math) | free gate, cooldown/daily-limit tables |
| `workstreamPooling.ts` | ContextWorkstreamPooling | tag rules, pooled-fact scoring, prompt sections |
| `tcrs.ts` | TaskContextualResurfacingService | legacy resurfacing pipeline + interruption gate |
| `subjectBinding.ts` | ContextSubjectBindingService | hash→subject matcher, 90s recent-context bind |
| `notificationSettingsSync.ts` | NotificationSettingsSyncCoordinator | revision journal, hydrate rules, backoff |
| `settingsSyncWiring.ts` | (wiring) | appSettings journal + mutation listener + startup reconcile |
| `service.ts` | (composition root) | flags, adapters (lane/tools/graduation), instances |
| `directorAssistant.ts` | ProactiveAssistantsPlugin seam | the coordinator peer + path routing |
| `register.ts` | — | idempotent bring-up |
| `../../ipc/contextBucketSchema.ts` | ContextBucketSchema | the 10-table DDL |
| `../../ipc/contextBucketStore.ts` | ContextBucketStore + destination binder | visits/buckets/facts CRUD, snapshot, GC |
| `../../ipc/proactivityLedger.ts` | ContextDeliveryAuthority (persistence) + candidates | reservation ledger, armed candidates, pools |

## Load-bearing invariants

- **Fence discipline**: every store write revalidates (visitID, generation,
  poolEpoch, outcome) and reports staleness as null/false; callers drop state.
- **Grounding**: non-silence requires ≥1 validated own-bucket entry ref AND ≥1
  validated fact id; retrieved refs are additive citations, never substitutes.
- **Budget**: one reservation per (visit, bucket version); suppressed/failed
  rows never count against the trailing-24h budget; terminal rows are immutable.
- **Cache stability**: the stable prompt's bytes (constant header, verbatim
  frozen segment) are a prompt-cache prefix — do not reorder or re-encode.
- **Privacy**: raw titles/app names never reach TCRS events (sha256 only) and
  the wire snapshot carries only canonical subject ids + signal enums; frames
  that failed `mayAnalyzeFrame` never reach extraction (coordinator contract).
- **Session hygiene**: pin `getSessionEpoch()` at job entry, re-check before
  every write; `onSessionReset` drops all in-memory director state.

## Flags (service.ts)

`contextDirectorEnabled` (Settings toggle, default OFF) is the pipeline master;
`OMI_FORCE_CONTEXT_BUCKETS` overrides for dev. Destination routing and the
retrieval hop ride the pipeline (env-disable with `OMI_FORCE_BUCKET_DESTINATIONS=0`
/ `OMI_FORCE_BUCKET_RETRIEVAL=0`); departure evaluation, workstream pooling,
and armed candidates are hard-off unless env-forced, mirroring mac production.
