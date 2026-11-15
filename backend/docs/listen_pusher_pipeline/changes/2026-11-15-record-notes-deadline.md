# Complete recording notes use the recording clock and retain a deadline

Notes urgency now uses the native, non-partial recording's trusted end time
(`record_finished_at`, copied from conversation `finished_at`). Per-unit
`fresh_capture` remains a merge classification and cannot suppress a complete
recording's immediate notes wake when fresh stamping is staged off. The
follow-up hint's existing freshness requirement is unchanged. Every sibling
receipt, producer barrier, revision, custody and processing-hold gate still
applies to the immediate completion wake.

A completion-owner marker previously had no notes bound when a sibling stayed
held, dead-lettered or never produced a result. On the first projected text
for each canonical output, its existing enrichment outbox now receives one
normal settled fallback in the same transaction as the ready receipt. The
existing ledger records that output once, so later siblings and retries cannot
renew the fallback or multiply notes updates. Completion can advance the same
obligation to now. No new poll, queue, worker or Firestore index is added.

The sibling-wait scheduling bound starts at the first projected text: 120 seconds
for first notes and 600 seconds for a refresh under current policy. The refresh
request is capped by the existing processing-hold ceiling of 3600 seconds.
An earlier existing obligation stays earlier; existing sync/merge holds keep
their own policy. Privacy/producer/processing holds, dispatch outages and LLM
compute remain separate gates; no notes-written SLA is implied. There is no
eligible transcript when no unit has projected. After the deadline the normal
settled path may summarize the available partial text. If the final sibling
arrives after that run, completion requests one final refresh.

An ordinary binding therefore has one delayed obligation plus one completion
update, independent of its 1..128 input units. These coalesce to one paid notes
run if completion wins the deadline, and at most two per output if a sibling
arrives afterwards, excluding existing provider/model retries and other
producers' work. Rollover into K output conversations has at most 2K runs.

Rollback: turning `RECORD_NOTES_EAGER_ENABLED` off affects recordings admitted
afterwards; recordings already admitted finish under the completion marker,
bounded by the existing settled fallback above. The ledger marker is durable
across age, flag changes and process restarts. No data migration is required.

The fallback adds one outbox read/write and one ledger write per distinct output
relative to completion-only scheduling; the receipt already had a write. At R
outputs/hour it adds R reads/hour ($0.51 * R / 1,000,000 per hour), and no recurring
poll reads. GPU images, fresh-stamping deployed values and roll order are
unchanged; this executes in CPU projection services.

Coverage includes fresh merge off with a 15-minute recording, days-old backlog,
held/dead/missing sibling deadlines, delayed wake durability, flag-off drain,
128-unit coalescing, rollover, and all preexisting immediate-wake hold gates.

## Composition with the lifecycle ledger and tunable processing hold

Merged main 7f944b6d38059 keeps `record_admitted_at` once per capture and the
ledger CAS after the real seal transaction. `record_sealed_at` stays in the
actual closure transaction and advances only when an open capture is sealed;
it is not replaced with the ledger write time. Recording-end eligibility still
uses `finished_at`; ledger `end_at` and `home_ready_at` retain main's outcome
semantics.

An active processing hold owns its existing absolute quiet/deadline clock.
Complete-record notes reuse `processing_hold.admission` on the canonical row
already read by completion, so an elapsed hold does not acquire another 600
seconds of settle. An existing outbox sync/merge hold keeps its deadline and
flags; a notes mark does not reassert them as a new content arrival. Earlier
first-summary delivery still passes the same consumer hold check before paid
work. These paths update the same coalesced obligation; the previous one-run
normal / at-most-two late-completion budget is unchanged. This composition adds
no producer Firestore reads/writes, polls or paid obligation. Earlier delivery
can cause a consumer deferral or stale-token read; that downstream delta is
unmeasured.

Projection admission-provenance instrumentation retains the bounded direct
follow-up hint and the same four slots. Fresh guard cadence is independent
observation; `RECORD_FRESH_MERGE_ENABLED` remains explicitly false in every
deployed dev/prod reader and worker values. No GPU worker image is rolled.
