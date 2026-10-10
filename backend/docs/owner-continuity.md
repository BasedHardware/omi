# Live owner continuity: rollover and reconnect

Owner recognition is free on every plan. Automatic naming of other people still
requires the existing paid entitlement. A continuity hint is neither enrollment
nor manual receipt authority and never trains a profile.

## What the old rollover counter means

The supplied 11.9-hour snapshot has 1,072 automatically carried owners and 1,005
mapped owners not carried: 48.4% of those two owner outcomes are `none`. This is
not necessarily a 48.4% loss of owner identity in the new conversation. The
counter visits **every old mapping**, including historical provider epochs and
automatic mappings superseded by copied manual decisions.

`SpeakerMatcher.refresh_for_conversation` emits one
`live_speaker_rollover carried=<...> target=<...> reason=<...>` log alongside each
existing counter increment. Values are closed and no account/device identifiers
become metric labels. Old queries on `omi_live_speaker_rollover_total` keep their
meaning. These are the complete drop categories:

| Reason | Why an old owner mapping is not automatically carried |
| --- | --- |
| `no_scope` | The rollover caller has no active provider scope or no eligible donor to bind to it. |
| `scope_changed` | The old voice belongs to another provider epoch, or the provider restarts while the donor/profile reads await. Diarizer integers cannot cross that boundary. |
| `donor_unavailable` | No eligible previous row, a failed donor/receipt read, or the refreshed donor disappeared. |
| `donor_authority` | A shortened live owner proof has lost its original donor receipt revision, enrollment or readable authority. |
| `donor_ineligible` | The old conversation is deleted, discarded, or locked, initially or on the reread. |
| `manual_override` | Owner reservation, a voice rejection, or a positive voice-wide manual decision in either donor/current receipt takes precedence. A copied manual owner can preserve identity even though the old automatic map counts `none`. |
| `no_evidence` | A mapping has no accepted owner decision/centroid/evidence backing it. This now abstains instead of indexing missing state. |
| `profile_unavailable` | Speaker ID is disabled or the enrolled owner cannot be loaded, including bounded retry exhaustion, missing/invalid print/audio, or excluded onboarding/custom-STT/multichannel/profile-opt-out mode. |
| `profile_changed` | The owner enrollment changed during the boundary; equality is exact, not an acoustic tolerance. |
| `stale_generation` | Teardown/clear moved the matcher while refresh was awaiting I/O. |
| `voice_capacity` | The lifetime voice/held-lock admission bound prevents restoring evidence. |
| `current_evidence` | That integer voice already has fresh current-conversation evidence; old evidence cannot overwrite it. A fresh accept is not old-map carry. |
| `voiceprint_rejected` | The retained centroid fails current enrollment verification: invalid/dimension-mismatched print, threshold, or runner-up print margin (including a newly loaded paid person). |
| `owner_contended` | The owner cannot beat other evidenced voices by the existing joint margin, or a current manual owner reserves the identity. |
| `manual_not_copied` | The old map was manual, but its voice id was absent from the copied manual receipt. |

For the last category, `carried_receipt` can omit a voice because the scope/donor
is missing, its segments lack valid scoped provider labels/placed audio, a label
maps to multiple integer ids, no winning receipt covers it, the newest winners
conflict, the winner is segment-only, or a previously carried decision names an
obsolete scope. Rejections/different decisions are not proof of carrying the old
automatic identity. `manual` and `automatic` are successful outcomes; `non_owner`
explains the separate person drop series. `not_restored`/`not_eligible` are bounded
catch-all diagnostics for incomplete or unreported state.

Without reason observations, a numerical attribution to any category would be
invented. The leading code-based hypothesis is `scope_changed`: acoustically
reconciled owner voices from multiple provider epochs can coexist in the old
map, while only the active epoch can carry. A near 1:1 carried/dropped split is
consistent with that mechanism. `manual_override` and profile acquisition failures
are secondary candidates. Deliberate re-enrollment, deleted/locked donors,
capacity, and tightly timed I/O races should be smaller absent a separate incident.
Use counts of `target=owner carried=none` grouped by `reason` to test this ranking.

The correction retains the entire eligible same-scope evidence roster through
rollover, including non-owner/unknown competitors, then recalculates distances
against the completed eligible print roster before joint arbitration, even when no old owner qualifies for carry. In
particular, a paid-to-free transition cannot discard a previously named peer's
acoustic competition. Retained non-candidate voices remain competition-only across every later arbitration, profile revalidation and cache publication. Five fresh current-conversation seconds must authorize a new label; retained peer clips cannot satisfy that floor.

## Acoustic reconnect handoff

The scope is `(authenticated uid, client_device_context.client_device_id)` from
existing per-install platform/hash headers. Missing device identity disables
handoff; recording/conversation ids and diarizer ids are deliberately excluded.
The reconnect admission bucket already uses this same account/device key and a
900-second idle lifetime. Handoff uses a much shorter **120 seconds since recent
accepted scoped speech**, covering ordinary network retries and app restarts
while avoiding a long idle-session identity hint. This is a conservative chosen
policy, not an empirically measured acoustic expiry.

An automatic, jointly accepted owner on the active provider epoch with at least five independent embedded
seconds can publish one normalized centroid and the exact enrolled-print digest.
New scoped transcript observations refresh its recency; repeated segment ids do
not. An idle matcher tick refreshes the cache only after new observations, with
one receipt read at most every 30 seconds. No extra embedding calls are made for
mapped speech. Manual reservations/rejections and persistence blocking withdraw
publication. Rollover retains the observation timestamp rather than renewing it
just because a new conversation row was created.

The private cache uses the same strict per-user AES-GCM audio framing as existing
speaker-embedding cache objects, in shared Redis rather than GCS so expiry and
cross-pod handoff are atomic. It stores no plaintext audio/vectors, has a 16 KiB
payload cap and 120-second physical TTL. Hashed account/device keys contain no
raw identity. A generation token (no voice data) expires after 24 hours; a socket
older than that fails closed for publication. Redis calls have 250 ms connect/read
bounds and run in the existing DB executor.

Each capsule also includes encrypted donor conversation, voice/scope and manual receipt generation. Every shortened acquisition reads the donor's current eligible row and strict manual receipt; any committed receipt-generation change, missing/ineligible donor or failed authority read revokes the hint, including after consumption and after the donor socket closes. The existing assignment/rejection transaction supplies the durable version fence; no socket callback is required. Accepted short owners retain that proof for same-scope rollover beyond the capsule TTL, and recheck its profile and durable manual authority on mapped speech, profile revalidation and rollover. Because mapped voices skip the embedding queue, new transcript observations also trigger an idle authority check at most once every 30 seconds; short owners remain excluded from capsule publication.

The final awaited transaction snapshot covers receiving and donor authority before shortened acquisition, rollover, or roster revalidation publishes an identity. One socket consumes one capsule, so the returned snapshot covers its hint and accepted proofs; mismatched proof provenance fails closed. After this read the matcher rechecks generation and rebuilds current evidence, then arbitrates and publishes synchronously. Provisional query scores remain local through receipt and authority awaits: cancellation cannot leave a shared distance row without its decision, and a different voice can still finish ordinary recognition while the probe waits.

Opening a socket atomically consumes the previous capsule and advances the
writer token. Concurrent opens consume at most one donor; late older sockets
cannot republish or delete newer evidence. Per-socket monotonically ordered publication revisions persist across deletions and fence executor writes that finish after cancellation and a newer withdrawal. The hint can be consumed while the
previous socket is still draining, without an unauthenticated continuity claim.

A new voice can use **two fresh embedded seconds** only if it passes both:

- Current enrollment verification at the unchanged 0.65 threshold and 0.10 print margin.
- Cosine distance below 0.35 to the recent session centroid, stricter than the existing 0.50 cross-provider grouping boundary.

It must then pass the unchanged 0.10 joint voice margin and current manual
receipt guards. The donor is never blended into the fresh query. Rejected short
voices remain arbitration competitors and resume the normal five-second floor;
A failed one-second accumulation remains pending; a failed two-second shortcut resumes normal five-second evidence acquisition. Non-owners cannot use the shortcut. Missing/corrupt/expired cache, changed profile,
or another account/device follows ordinary matching. Two seconds and 0.35 are
conservative starting points requiring post-deploy false-accept/miss evaluation;
no real-audio calibration or production validation was performed in this PR.

Once a reconnect accept is established, same-provider-scope rollover rechecks
its centroid against current prints and joint competition without requiring the
old socket hint to remain alive. The TTL applies to new-socket acquisition.
Shortened accepts cannot seed another handoff. At least five independent seconds
are required for a new donor, preventing indefinitely chained pseudo-evidence.
Unplaced audio, <2-second fresh evidence, cache outages, missing device headers,
and long gaps remain unknown until normal evidence is available.

## Measuring the result

`omi_owner_reconnect_total{outcome,reason}` has closed outcomes
`attempted|accepted|rejected`. `attempted{reason="lookup"}` counts eligible socket
cache lookups (including missing device); `attempted{reason="acoustic"}` counts
actual shortened voice decisions. Use the acoustic attempts as the acceptance-rate
denominator, not the lookup count. Rejections distinguish `no_device`, `absent`,
`corrupt`, `unavailable`, `expired_or_profile`, `donor_authority`, `acoustic`, and `arbitration`.
Accepted decisions have `reason="accepted"`; later joint withdrawal remains
visible through existing live decision/contention and final conversation metrics.
No production metrics or account data were read for this implementation.

The final decision reads the receiving conversation, original acoustic donor,
and (at rollover) immediate donor in one Firestore transaction snapshot, bounded
to three receipt/privacy projections. Corrections committed before that snapshot
are honored across all three authorities; separate receipt objects from earlier
awaits cannot authorize publication. A missing/ineligible document or failed
snapshot vetoes all identity publication and owner continuity renewal, including
earlier positive manual receipts and ordinary five-second automatic evidence.
Unavailability is a separate flag, so an independently read receiving receipt
retains its known rejections. One shared publication gate applies those known
rejections/retractions, then stops acquisition, reevaluation, mapped-voice renewal
and rollover when authority is unavailable. The matcher rechecks
its generation and rebuilds current evidence after the transaction, then
arbitrates and publishes without yielding. Ordinary matching with no short proof or rollover keeps its
existing receipt read and five-second policy.
