# Weekly dogfooding quality: remaining boundaries

LIFECYCLE: permanent

This proposal tracks the scope decisions for API/MCP feedback items 1-16 and
quality categories 01-09 from the week ending 2026-11-01. It contains no account
records, transcript excerpts, or private identifiers. PRs own implementation and
review state; this document describes the boundaries and acceptance evidence.

## Scoped safeguards

The deterministic relevance rule rejects only runs of at least three exact ASR
outro phrases when every nonempty segment is on the narrow lexicon. Mixed real
speech, a single sign-off, unknown phrases, and quoted longer sentences abstain.
Existing photo, calendar, explicit user restore, and processing-mode protections
remain authoritative. No raw transcript is deleted. This does not repair a
multi-hour capture with a few real lines mixed into hallucinations.

Notes and daily-summary instructions distinguish calendar plans from completed
outcomes and background speech from owner participation. Both action-item prompt
variants admit explicit owner reminder requests, including errands, and exclude
current-session agent commands unless there is a later owner commitment. The
memory extractor routes reminder-only requests away from durable facts. A date
without a time stays in task context rather than inventing an hour. These are
prompt-contract changes, not measured model-quality improvements.

## Larger changes and acceptance evidence

**Wearer and speaker identity (API 2; quality 01).** Hard gating on current
`is_user` values would hide legitimate calls when the remote participant is
misassigned. Keep source-local speaker keys and unknown identity. A wearer anchor
needs synthetic dual-channel calls, nearby meetings, missing enrollment, and
speaker fragmentation cases with known identity; measure both false owner claims
and lost owner speech before using it as a summary/memory gate. Calendar rosters
may corroborate spelling but cannot establish voice identity.

**Cross-device deduplication and segmentation (quality 04/05).** Time overlap alone
cannot prove a common conversation. Extend the existing capture-group authority
only with evidence of the same event and sufficient source text agreement. First
replay synthetic same-call dual-device captures, two independent overlapping
calls, repeated short phrases, delayed uploads, and midnight boundaries. Preserve
source identities, transcript segments, task provenance, and reversible merge
lineage. Concurrency and retry tests must prove one survivor without lost text;
measure duplicate reduction and false merges separately. Echo removal should
require matching content and overlapping source timing, not a shared speaker label.

**Summary scheduling and pending cards (API 6/9; quality 05).** Generation time is
only an upper bound on the input snapshot. A settled-day recap requires durable
capture/finalization watermarks, a bounded after-midnight regeneration trigger,
and idempotent replacement. Replay a late prior-day card and a failed generation;
prove the recap updates once without duplicate notifications. A list pending count
needs the processing ledger's day/window contract rather than an inferred count
from currently visible cards.

**Memory reconciliation (API 3).** Storage creations include suppressed, rejected,
archived, superseded, restricted, and duplicate-store rows. A fetchable count must
use the same visibility/sensitivity/activity filters and authorization as the
caller's memory list, with an explicit as-of time. Reuse that policy path in a
bounded count API; report incomplete counts instead of silently falling back to
storage totals. Test canonical/legacy twins, rejected items, archives, grants,
late arrivals, and page exhaustion. Summary reads currently label the storage total
and leave the unmeasured fetchable count null; historical totals are not rewritten.

**Sync and extraction timestamps (API 7/8).** Observed screen timestamps do not
prove that earlier captures synced. Devices must send an acknowledged per-device
high-water mark plus capture enabled/disabled intervals. Test delayed and out-of-order
batches, clock skew, and disabled capture. Source time can be exposed from evidence;
legacy evidence creation timestamps sometimes alias capture time, so extraction
time remains unknown unless explicitly recorded. Persist an extraction receipt
at the producer boundary before claiming a historical extraction timestamp.
KG bookkeeping no longer advances the product edit time; a broader no-op edit audit
needs synthetic idempotent writer replays, including connector and backfill paths.

## Item disposition

| Feedback | Scope and what settles the remainder |
| --- | --- |
| API 1 | Whole-detail batch paging and optional rosters; regression and HTTP wire-budget tests. |
| API 2 | Identity redesign deferred; the wearer-anchor acceptance cases above settle it. |
| API 3 | Storage/visible count distinction exposed; policy-matched counting remains as proposed above. |
| API 4 | Summary snapshot cutoff exposed; completer/source history and missing-conversation provenance need an event contract and write-path migration. |
| API 5 | Existing stored call evidence stays nullable; better call/calendar linkage needs client evidence and labeled linkage replays. |
| API 6 | Processing watermarks deferred; ledger-backed late-finalization replay above settles it. |
| API 7 | Capture completeness is unknown; per-device observed bounds added, acknowledged sync watermarks still need a device protocol. |
| API 8 | Source timestamp projection and KG bookkeeping fixed; historical extraction receipts and all-writer no-op guarantees remain as proposed above. |
| API 9 | Generation cutoff exposed; automatic after-midnight regeneration needs the scheduling contract above. |
| API 10 | Deep-read timezone option deferred; timestamp equivalence is valid today, and a shared projection with offset compatibility tests would settle it. |
| API 11 | Language classification deferred; a labeled multilingual/short-utterance ASR evaluation is required. |
| API 12 | Device counter sum labeled as potentially overlapping, distinct from elapsed observation estimates. |
| API 13 | Dotted structured fields, short aliases, and discarded projection supported. |
| API 14 | Duplicate flat detail removed; nested conversation and stable item id retained. |
| API 15 | Identifier migration deferred; opaque IDs already work and need an alias/migration compatibility contract before changing them. |
| API 16 | No reported failure; no code change required. |
| Quality 01 | Speaker identity deferred; no heuristic relabeling or wearer hard gate. |
| Quality 02 | Exact repeated outro safeguard added; mixed hallucinations, energy/VAD, language consistency, and bystander hard gates require labeled audio evaluation. |
| Quality 03 | Media classification deferred; foreground-player plus trustworthy participation evidence must beat overlapping real conversation on synthetic replay. |
| Quality 04 | Cross-device/echo dedup deferred; common-event evidence and reversible lineage tests above settle it. |
| Quality 05 | Calendar context/outcome prompt distinction added; segmentation, reliable durations, pending cards, and settled-day recaps need lifecycle work. |
| Quality 06 | Reminder/agent-command memory prompt exclusions added; existing incorrect records remain untouched, and attribution/vocabulary improvements require the owner-evidence evaluation. |
| Quality 07 | Explicit reminder and agent-command rules added; date-only scheduling, reliable multi-step recall, wrong addressees, and general triviality filtering need a scored synthetic task set. |
| Quality 08 | Vocabulary biasing deferred; validate per-user terms at the ASR boundary without cross-account leakage or false substitutions. |
| Quality 09 | App performance/capture/UI reports deferred; each needs a platform-specific synthetic reproduction and the owning client guide's checks. |

All validation for these changes is hermetic or local. No production account data,
production API calls, model-quality scoring, deployment, or user messages are part
of this work.
