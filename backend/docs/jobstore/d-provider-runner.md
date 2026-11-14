# Ordinary provider driver: dark source boundary

2026-11-14, SCA-1959 / PR25215. This is source composition, not production
installation, activation, fleet qualification or closure of the first P1.
Firestore remains the privacy authority. Copy/serve/activation remain held.

`routers.batch_provider_stt.run_typed_provider_async` returns immediately when
no runner is supplied. `TypedProviderRunner` also defaults to disabled. The
ordinary Cloud Tasks consumer and its existing FS/shadow factory are unchanged.
There is no new env flag, per-unit provider outbox or document-mirror switch.

The explicit host composition supplies an already admitted ProviderHandoff,
the existing health adapter, result artifact factory, and scheduling bounds:
count, backlog share, lease, effect lease and partial wait. It does not derive
new class, owner-turn, funding, lifetime or vendor policy. The typed Units
claim query keeps its existing class/owner-turn/capture ordering and can filter
before leasing to the ordinary unsupported-language Modulate cohort. Other
cohorts are not leased by this runner and no PG row falls back to FS ownership.

For each original claim, TypedProviderStage reuses the actual ProviderSttStage
preparation and async call phases, rather than invoking transcribe in isolation:

1. Revalidate original SQL source/admission and registered effect.
2. Existing funding gate, actual authorized encrypted input fetch, inspection,
   second funding gate, served-table candidates and health/cap reservation.
3. Original durable attempt identity and immutable intake usage period.
4. Existing allowance Operation and reserve_async; real FenceTicket.START on
   db_executor immediately before the one awaited paid POST.
5. Actual ordinary ArtifactStore resumable publication, original generation and
   lifetime; paid COMPLETE/typed terminal/counter/full sibling seal share COMMIT.
6. Return only a fully sealed recording identity to the customer dispatcher.
   ProviderProjection.project_recording uses actual ordered customer assignment,
   enrichment/usage/ledger, completion receipt and grouped PG acknowledgement.

ProviderResultReader reconstructs read authority from original terminal unit,
published upload, attempt/admission/effect and handoff rows after worker exit.
It never registers a new effect or reads a session capability. Actual fresh
A1/walk/A2, original P/PC, matching F token/epoch and before/after object checks
remain in ProviderUpload. All SQL slots/owner guards end before remote I/O.

The joined path exposed a real missing discriminator: production provider
payloads carry recovery_version=1, and OrderedMerge marks provider result log
entries accordingly. The private view now applies that same discriminator.
An older private view without it refuses validation; missing/changed views are
never reconstructed to bypass deletion. No new retained copy or TTL is added.

Lost SQL replies resolve only against the original committed result and its
published upload. Publication without terminal COMMIT resumes that original
result; unknown paid/session outcomes refuse another POST/PUT. Lease expiry
does not grant paid replay. Unique FS intake/repair context and every original
PG/upload/journal custodian remain retained.

## Qualification and remaining installation gates

Actual emulator/private PG cases join original admission, encrypted input,
funding/health/cap/allowance ordering, local resumable result publication,
terminal, real customer assignment/usage/receipt/grouped ack and customer
reader restart. Negative cases cover both funding denials, health/inspection/
silence, served failover, BYOK dequeue exclusion, privacy/token/epoch changes,
foreign results/owners and lost paid/terminal replies. Four os._exit cases
exercise after paid response, after publication, and both sides of terminal
COMMIT. Paid network, billing/VAD and local storage transport are synthetic;
this is not remote GCS C4 or funded fleet/budget evidence.

Still missing: production admission/cohort selection, host scheduler/runner
construction and durable dispatch/recovery of intents, pre-START deferrals,
unknown attempts and completed recording tasks. A pre-START refusal retains
its original claim; automatic rediscovery is not implemented. Native, partial,
coalesced, recovery, BYOK, empty/failed/held and multi-vendor attempts need their
typed adapters. Configured alternative candidates refuse rather than changing
the served policy; this is not a recommendation to disable fleet failover.
Legacy FIFO/DRR/head-wait behavior remains unchanged.

Original intake/staging/late-audio/session all-copy proof, remote C4, final
destructive typed PG/journal barriers, full reverse/cohorts/certificates,
account close/drain/recovery injection, paging/scheduling, every G2/P21-P25 row
and accepted SCA-1690 fleet qualification remain gates. Historical staging
deadline failure and three required outbox failures are not waived by this
driver. Final exact-head receipts state current results and retain failures.
No savings are booked and source readiness remains false.
