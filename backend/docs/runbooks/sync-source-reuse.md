# Exact source-file reuse for sync uploads

Anonymous sync uploads can contain the same original file in different bundles.
Whole-bundle idempotency does not recognize that source identity. Ordinary
clock-trusted uploads with a device identity and at most 64 files now decode
at original file boundaries. The server HMAC binds owner, device, filename
(including codec/capture stamp), explicit epoch metadata, original bytes,
decoder version, canonical samples and exact split bounds. Equal timestamps,
text, silence PCM, and overlapping envelopes alone never qualify.

Files repeated exactly within one upload contribute one input. A different
file, a partial file, or an uncovered tail remains independent input. A file's
unit splits are retained in full; no text is split on midpoint containment.
This changes packing granularity, so monitor unit admission and queue latency
as well as the source reuse counters. Uploads above the bounded file limit,
unknown clocks, coverage trimming, alternate decoders, explicit targets,
coalesced receipt imports and native recordings keep their existing path.

## Canonical ownership and billing

`batch_pipeline_<stage>_source_reuse` holds one owner-scoped, bounded source
receipt. The first placed result in the owner's committed projection order
claims it in the same transaction as assignment. Every later writer rereads
that document before writing text. A racing job may have computed already;
it cannot publish another copy. An unfinished owner is a wait, not a completed
transcript. This slice does not reserve in-flight compute ownership across
bundles: two uploads admitted before either has projected can both compute.

Admission aliases require a current committed success/silence result, all
projection parts ready, the original content ledger completed under its own
funding attribution, current privacy generation and source/output fences, and
unexpired artifact registrations. Intake also reads/authenticates the result
object before reuse. A missing object follows normal processing; a dependency
lost after alias acceptance holds the alias rather than redispatching it.

Each accepted alias retains its own new encrypted audio and a small encrypted
result marker. It enters `result_ready` outside both the GPU and provider
queues, makes no language, ASR or summarization call, and projects a pointer to
the existing outputs with zero new speech seconds. Ordinary completion uses
that zero receipt, preserving existing month and partial-settlement fences.
Historical charges are unchanged. No existing transcript, annotation,
translation, segment ID or merge ancestry is rewritten.

Source/alias markers require result protocol 2 with a source-reader marker.
Older projectors refuse them before reading a marker as a model result. New
workers can process normal source-key jobs; an image rollback must retain new
projection readers to drain accepted protocol-2 work. Releasing an old image
is not a safe way to make accepted aliases into ordinary paid work.

## Custody and privacy

Source equivalence is transcription authority only. It produces no covered
ACK, WAL handoff, reclaim or source-frame custody receipt. The existing upload
status path acknowledges only normal durable progress. Newly uploaded audio
is staged before alias admission. Cancellation leaves the existing staging
outbox responsible for cleanup; no alias job or paid dispatch is created.

Original input and every canonical output privacy dependency travel on the
alias job, result and both artifacts. Registration checks them before storage,
authorization checks them after storage, admission checks them transactionally,
and projection rechecks them before committing. Account/protection generation
changes and conversation tombstones cannot resurrect a deleted result.
Both account purge and resumable conversation purge include source receipts;
artifact dependencies are present before upload, so a crash cannot orphan
private content outside erasure discovery. Receipts expire at the ordinary
45-day ledger horizon; artifact availability remains bounded by existing
24-hour completion retention. No retention extension is introduced.

## Kill switch and observation

`BATCH_SOURCE_REUSE_ENABLED` defaults on. Set false to stop new source-proof
packing and admission aliases. Malformed explicit values also stop new
admission. Previously accepted source-key jobs retain their projection fence;
accepted aliases remain non-runnable paid work and finish through the same
pointer path. The switch never erases custody receipts or rewrites charges.

Counters have a closed `event` label and no owner/source/content identifiers:

- `omi_batch_pipeline_source_reuse_total`: reused, avoided_asr_input,
  alias_wait, alias_refusal, uncovered_tail, duplicate_projection_refusal,
  custody_failure.
- `omi_batch_pipeline_source_reuse_seconds_total`: source input seconds for
  the corresponding duration-bearing events.

`avoided_asr_input` counts accepted pre-dispatch alias input envelopes;
`reused` counts newly committed projection aliases (including already-computed
racers). These are not GPU runtime, padded/VAD ASR window seconds or dollars.
Repeated waits/refusals count attempts. A lost commit reply/process exit can
undercount observed transitions. `uncovered_tail` is the full undecidable unit
in this whole-file slice; it never authorizes trimming. Fleet savings require
window/runtime or vendor evidence alongside these counters.

## Deferred work and historical dry run

Native/anonymous cross-lane discovery needs authenticated frame/byte mapping
against retained native sources, independent clock transforms, durable pending
compute waiters and deletion-aware result dependencies. Partial overlaps and
new tails inside a file need range-aware billing and word boundaries. This PR
abstains from those equivalences and does not broaden lexical filtering.

Proposed operator dry run, not an automatically enabled reprocessor:

1. Pin a short creation window and a bounded page/document budget. Include only
   rows with immutable source-job or merge evidence; read under current owner
   and source/output privacy fences. Do not fetch/decrypt more account data
   without the assignment authorizing it.
2. Join retained original-file/frame proofs to committed source results. Emit
   aggregate proven/unknown/protected counts, proposed view exclusions and
   uncovered input seconds. Missing proofs remain unknown.
3. Independently verify precision, annotation preservation, coverage and billing
   attribution. Stop on any generation, correction, ownership or revision change.
4. Apply only a separately approved reversible source-ownership view or revision-
   fenced canonical pointer. Preserve original text/IDs/audio/ancestry and
   historical usage. Summary regeneration uses ordinary paid-work admission
   only after canonical transcript verification.

No historical reprocessor is run by this change. A packet containing only
source/time associations and no exact source proofs yields zero proved
historical exclusions, regardless of its overlap opportunity estimate.
