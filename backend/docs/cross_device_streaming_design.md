# Streaming cross-device reconciliation: remaining work

Status: proposed, 2026-10-26. Owner: capture/transcription initiative. This note
does not enable a cohort or authorize a production write.

## What exists

`utils/capture/coverage_crossdevice.py` runs at completed-conversation
finalization, independent of the old desktop-meeting + pendant special case.
Different sources, or the same source with two known different device IDs, can
qualify. Unknown device identity is not a wildcard. Ordered shared speech must
confirm every member pair; time overlap only discovers candidates. A secondary
with any unmatched speech remains visible. Original transcripts and audio stay
intact, including when a group is displayed as one event.

The bounded adapter reads at most seven snapshots and performs at most twelve
pair checks. It revalidates transcript fingerprints, metadata, privacy,
membership and group revision in the existing group writer. Exact secondary
capture keys may alias already committed primary coverage. A query revalidates
the alias. None of this proves a byte/sample mapping from wall-clock overlap.

Current election prefers the pendant, then retained SNR/confidence, duration and
stable identity. Those quality measurements are optional, so this is not yet a
general best-audio election. Near-duplicate whole captures can collapse; unique
complementary channels do not yet combine into one higher-quality transcript.

## Missing work and proposed boundaries

1. **Session rendezvous.** Index active captures by authenticated account and
   exact device/session/channel/clock-epoch keys. Account-local time overlap
   proposes candidates; it grants neither speaker identity nor suppression.
   Keep the existing desktop-call path until the generalized path proves its
   complementary-remote-channel cases. Unknown keys retain separate captures.
2. **Partial-window alignment.** Use bounded finalized text/audio windows with
   source-frame receipts and transcript versions. Never suppress mutable ASR
   partials. Share the completed matcher and pairwise guard rather than invent
   a second text-similarity threshold. Silence, playback on two devices,
   clock skew, revisions and unique interjections need explicit negative cases.
3. **Quality election and assembly.** Persist bounded server-produced SNR and
   word-confidence observations. Elect one primary per proven shared window,
   preserve distinct remote/local channels, and append only proven unique
   secondary speech in temporal order. Keep original segment IDs, scopes,
   source provenance and manual corrections. Missing quality data abstains
   from a quality claim; it must not invent an owner anchor.
4. **Durability and socket delivery.** Wire the existing
   `coverage.committed_events` alias receipts to the authenticated secondary
   socket only after the primary commit and alias transaction succeed. Bind
   each event to full capture key, group revision and transcript fingerprint.
   On reconnect, query the same authority. A dropped socket notification cannot
   release WAL; a retried notification cannot create a second commitment.
5. **One derived event.** Claim the existing finalization/derived-effect
   obligation for the assembled event. Revisions invalidate caches and aliases;
   retries reuse the existing claim. Do not regenerate notes or retranscribe
   both streams in shadow. Keep unique speech and its source reachable even
   if grouping fails or a user separates the group.

Implement as three reviewed slices: rendezvous/quality metadata with no serving
change; receipt-backed partial-window decisions and replay harness; then socket
dispatch plus derived-event convergence. A cohort alone cannot supply these
missing paths. No device/firmware retention change is part of this design.

## Acceptance and rollout

Use a synthetic three-device matrix (pendant, watch/phone, desktop remote
channel), then an explicitly approved owner pilot. Cover same-source distinct
devices, missing IDs, same-device retries, clock reset/skew, silence, repeated
media, overlapping meetings, unique speech, manual correction, deletion,
primary replacement and disconnect between commit and notification.

Require zero lost unique speech, false folds, identity/manual violations,
premature custody ACKs and duplicate derived deliveries. Positive denominators
must show actual examined duplicate and unique windows; absence of a metric is
not success. Measure duplicate/examined lines, custody receipt latency, sync
failures and vendor-paid seconds/tokens. Extra devices must not add duplicate
paid work; any net cost increase needs a cost offset or a lead ruling.

Use aligned producer/consumer cohorts and one full lookback window per step.
Rollback disables new admission and clears cohorts; committed audio, transcripts
and durable obligations remain. Group separation/restore/reprocessing may be
needed for persisted classifications or assemblies; changing a flag does not
undo them. Historical data repair requires separate authorization.
