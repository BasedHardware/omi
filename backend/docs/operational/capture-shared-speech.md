# Deterministic shared speech for overlapping captures

Owner: dazheng. Requested 2026-10-16. Review by 2026-11-15.

## Behavior and scope

`CAPTURE_SHARED_SPEECH_MODE=off|shadow|on` defaults to `off`. An account is
selected by the union of `CAPTURE_SHARED_SPEECH_UID_ALLOWLIST` (comma separated,
default empty) and `CAPTURE_SHARED_SPEECH_PERCENT` (stable salted account bucket,
default 0). Invalid mode/percentage fails closed. Flags are evaluated at the call
boundary, not import time. Setting mode alone admits nobody.

Off preserves the incumbent path and adds no reads, writes or decision logs.
Shadow preserves incumbent grouping and adds at most seven decrypted reads per
completion to evaluate six overlapping candidates, including same-source pairs.
On replaces automatic capture grouping for selected accounts with the new
sentence rule, including the complementary desktop-call policy. It still writes
ordinary advisory cross-source overlap hints; clients do not collapse those hints.
All modes leave existing groups intact. No historical scan or backfill is run.

The new rule can group same-source/same-device, different-device and unknown-device
pairs. Device equality is neither evidence nor a reason to reject shared speech.
Every admitted pair must have positive wall-window overlap. The existing query
and six-pair budget remain bounded; query saturation is degraded evidence, not
proof that all candidates were considered. The longest observed windows are
checked first, with ID tie breaking.

The writer remains `database.capture_groups.join_capture_group`, with the same
transcript fingerprints, expected windows, sticky Separate exclusions,
deletion/discard/closed fences, 12-member cap, and refusal to bridge two existing
groups. For the new rule, an entrant must also match every existing member;
all those transcript/window snapshots and the group revision are fenced in the
transaction. A long capture cannot transitively bridge two unrelated scenes.
If that proof exceeds the same seven-read budget, the rule abstains. It changes
group metadata only. Transcript, summary, memories, tasks,
sharing and effects are retained independently. Separate reverses presentation
grouping and prevents regrouping with former members. It does not undo manual,
sync or smart merges. Switching off stops future decisions; it does not dissolve
groups already created.

Flutter/macOS collapse loaded members behind one representative and retain access
to every recording. A singleton loaded member remains visible. Pagination still
counts original records. On can leave new unsupported cross-source pairs as two
rows, and collapse new same-source duplicates; old groups do not change.

The hook runs after successful persistence in REST/sync/from-segments processing,
and after the durable fanout fence in live/Cloud Tasks finalization. Deploy the
same revision/config to Cloud Run backend, backend-sync, backend-sync-backfill,
backend-integration, GKE backend-listen and pusher. No client release is required.
Smart merge remains separate. EXP-003 Jev concluded no-go on 2026-10-17 after
3 of 14 “same” calls were wrong (79% precision, below the preregistered 90%
bar); the re-summary half was dropped. Its log-only shadow was removed, and
this deterministic matcher remains the replacement.

## Matcher contract (overlap_shared_speech_v1)

1. Validate completed, retained captures and compatible lock partitions. Reject
   invalid capture windows. Unusable segment timing contributes no sentence
   evidence. Charge every word in those segments as distinct unshared vocabulary
   in the window Jaccard denominator, so dropping noisy lines cannot inflate
   similarity. This is a conservative lower bound; unknown words never add
   matched duration or words. Select whole trusted segments inside
   the actual wall intersection. Only sub-microsecond epoch-rounding noise is
   clamped to those bounds; it never contributes outside duration. A boundary-straddling segment
   cannot borrow all its words from outside the overlap.
2. Normalize Unicode NFKC, case, punctuation and straight/curly apostrophes. Ignore
   all speaker/own-voice labels. Require at least 30 words on each side in the
   intersection and token-set Jaccard at least 0.25. Jaccard alone never folds.
3. Compare lines whose wall starts differ by at most 15 seconds. Each accepted
   pair needs at least one second and eight distinct words per line, six shared distinct words,
   two shared ordered bigrams, token Jaccard at least 0.5, and an ordered LCS of
   at least 60% of the longer line's tokens.
4. Assign lines one-to-one, require monotonic line order, and count each normalized
   sentence once per side. Require two distinct matched sentences, 20 distinct
   aligned words, eight distinct shared bigrams, start-time support spanning at
   least ten seconds on both sides, and at least 15 seconds of union duration of
   matched lines on each side. Gaps/silence and overlapping duplicate lines do not
   add duration. Line duration is transcript evidence, not acoustic ground truth.

Captures with transcript correction flags/overlays abstain. A dedicated
single-snapshot read bounds stored encrypted/compressed input at 1 MiB and
decoded JSON at 2 MiB before parsing, then strictly decodes immutable segments without projecting
or reading mutable correction overlays. The transaction guard rechecks every
member's effective discard, completion, deletion/closed, correction markers and
lock partition. Unknown layouts and overflow abstain rather than claim a match.
Bounds per capture: 4,096 segments, 524,288 text characters, 64,000 selected words, 4,096
characters and 90 seconds per selected segment. Each pair check is capped at 16,384
line comparisons, 524,288 token-set operations and 262,144 LCS cells. Literal stored lists are checked for segment/text/field bounds before use. The core is
pure CPU, uses no provider and persists no lexical fingerprint or transcript.
At most 12 matcher calls run per completion, including group-member confirmation.
Changing cutoffs/version requires recalibration.

This deliberately misses noisy, clock-shifted, heavily resegmented or weakly
shared captures. It cannot determine the meaning of common background broadcast
audio from transcripts alone. Identical concurrent background speech is a safety
limitation to evaluate, not a claim of one semantic event.

## Calibration (2026-10-17, provisional)

Private inputs remain outside Git. Never copy cards, identifiers or text into
issues, PRs, logs or the knowledge base. Report aggregates only. David's `unsure`
labels are excluded from precision/recall and audited separately for folds.

Snapshot: 29 David labels (13 same, six different, ten unsure), 244 pair cards.
The cards omit segment ends, but the existing local pilot export retains them.
Joining the original timed transcripts through the existing prospective event
records, with September exports filling missing rows, reproduces the transcript
text in all 29 labeled cards exactly. No account read or new export was needed.
Earlier synthetic-duration and boundary-slop prototypes were discarded; the table below uses
original segment ends and the current strict-overlap matcher. Minimal exports
omit lifecycle/lock/correction metadata; content replays assume completed,
retained, unlocked, uncorrected rows. Serving admission may abstain further.

| Data and class | Decisive n (same/different) | TP/FP | Precision (95% Wilson) | Recall (95% Wilson) |
| --- | --- | --- | --- | --- |
| David, cross-source | 7 (5/2) | 2/0 | 100% (34.2–100%) | 40% (11.8–76.9%) |
| David, same-source same-device | 12 (8/4) | 2/0 | 100% (34.2–100%) | 25% (7.2–59.1%) |
| David, all | 19 (13/6) | 4/0 | 100% (51.0–100%) | 30.8% (12.7–57.6%) |
| September agent benchmark, cross-source | 52 (32/20) | 1/0 | 100% (20.7–100%) | 3.1% (0.6–15.7%) |
| September agent benchmark, same-source same-device | 43 (24/19) | 0/0 | undefined, no folds | 0% (0–13.8%) |
| September agent benchmark, same-source different-device | 1 (0/1) | 0/0 | undefined, no folds | undefined, no positives |
| September agent benchmark, all | 96 (56/40) | 1/0 | 100% (20.7–100%) | 1.8% (0.3–9.5%) |

For comparison, replaying the incumbent ordinary rule with its code defaults on
the original ends gives David cross-source TP4/FP2: precision 66.7% (Wilson
30.0–90.3%), recall 80.0% (37.6–96.4%). On the September cross-source set it gives
TP9/FP0: precision 100% (70.1–100%), recall 28.1% (15.6–45.4%). It accepts no
same-source pairs. These are policy replays, not historical group observations;
they do not include a nondefault containment/call policy or transaction conflicts.

No David different-device or unknown-device labels exist at this snapshot. No
folds on ten unsure labels; eight excluded benchmark pairs also have no
folds. The benchmark uses actual segment ends, but enriched old same-scene labels
include adjacent events without overlap (38/104), truncated layouts and clock
errors. It is a stress set, not a prospective shared-sentences truth set. The
single benchmark accepted pair is insufficient evidence of useful recall or safe
fleet precision. Its component-held-out split accepts 0/20 same with 0/14 false
folds; held-out recall is 0% (Wilson 0–16.1%). Cases share captures, so Wilson
intervals assume independence that the actual sample does not establish; report
them as descriptive only.

Two David negatives defeat a bag-of-words rule. Their start-only overlap-window bag-of-words Jaccards are 0.398
and 0.653. The former has zero strong line pairs anywhere; the latter has 16
strong line combinations, all at least 35.8 seconds apart (best exact line pair
47.8 seconds apart). Neither has a strong line pair within 15 seconds. Both remain
separate. These observations do not establish a TV/background-audio diagnosis.

The final rule accepts four David positives, including two same-source duplicates
that the incumbent cannot join. It rejects all six negatives and ten unsure
pairs. The accepted denominator remains too small to establish fleet safety.
Negative start values as small as 0.55 microseconds were verified to be epoch
subtraction noise and are clamped within one microsecond. Actual end overruns of
0.468 and 2.184 seconds, long compacted lines and zero/negative-duration text
supply no evidence; their words reduce the similarity lower bound instead of
vetoing otherwise strong independent sentences. Hard storage/work limits still
abstain for the whole pair. No score threshold was lowered to recover recall.

The first Luna review found out-of-capture boundary evidence, commit-time
eligibility/lock races and unfenced correction projections. The revised matcher
uses actual capture/overlap bounds (with only clamped microsecond arithmetic),
requires each supporting line to last at least one second, rejects mutable
correction captures without overlay reads, and checks all member eligibility and
locks inside the transaction. Early incumbent snapshot-conflict exits retain
their original read budget. New synthetic regressions cover each failure. A
second Luna review confirmed those fixes and found an additional pre-matcher
unbounded-decompression risk. The storage reader now caps encoded input and
uses bounded streaming decompression with EOF/trailing-data checks before JSON
parsing; overflow returns a static abstention. Synthetic tests verify that a
high-expansion payload never reaches the parser. A third read-only Luna review
of 8f407abf1dcb found no blocking issues, confirmed bounded decoding and the
conservative unknown-word penalty, and qualified dark/shadow only.
Thresholds favor false-fold avoidance: ordered, timed, distinct sentence evidence
and actual line duration are mandatory. Low global lexical overlap is allowed to
remain a false negative. Current evidence supports dark/shadow deployment only.
No claim of zero fleet false folds follows from zero observed labeled errors.

## Production rollout and rollback

Coordinator-approved scope (2026-10-17): deploy the four Cloud Run hosts dark
through workspace `bin/omi-deploy-prod wait-eligible` then `cloud-run`, approving
only this owner's run. Prepare the previous eligible release SHA as rollback
before dispatch and watch at least 15 minutes. Do not dispatch dedicated Pusher
or backend-listen deployments. Their default-off code follows the next regular
train owned by others; keep their mode off until the train carries the code.

Before the first shadow deployment, declare `CAPTURE_SHARED_SPEECH_MODE=off`
and `CAPTURE_SHARED_SPEECH_PERCENT=0` explicitly on those four Cloud Run hosts,
deploy and watch that release, and retain its eligible full SHA. The deployment
action defaults to merging environment variables; a feature-bearing release
that omits these keys cannot reset a later shadow value. The sidecar attachment
preserves extra environment entries. Use the explicit-off release for the normal
workflow rollback so it overwrites mode/percentage while retaining current
incident controls. See the [deployment action contract](https://github.com/google-github-actions/deploy-cloudrun/blob/v3/action.yml#L83-L91).
GKE overrides remain absent/default off throughout this qualification.

Land a separate runtime-env config PR enabling shadow on Cloud Run only, then
repeat the Cloud Run deploy and watch. Leave GKE settings absent/default off.
Capture served revisions, traffic and exact rollback commands before dispatch.
The prior eligible explicit-off release is restored through the same Cloud Run
workflow with its previous `release_sha`; an omitted-key release is insufficient
once shadow keys have been set. The documented incident-only Pusher fallback is
`helm --kube-context gke_based-hardware_us-central1_prod-omi-gke -n prod-omi-backend rollback prod-omi-pusher <previous revision>`;
do not execute it without an incident. No Pusher deploy is part of this rollout.

Watch request counts/5xx and fixed error signatures against the preceding equal
window on every touched service, readiness/restarts, and appearance of the new
`capture_shared_speech` line. Its JSON contains IDs, static categories/reasons,
numeric evidence, new verdict, incumbent ordinary would-join, existing-group
observation and write outcome; no text or lexical hashes. `current_would_join`
is the incumbent ordinary policy on checked discovery candidates; it is null
for corrected captures whose mutable overlay was intentionally not read, or
for snapshots that could not be decoded within the storage bounds. It is
not proof a
transaction would commit; `already_grouped` is a separate observation. The
complementary-call policy is separately identifiable through existing call logs.
Exceptions emit fixed `outcome=error` without exception text. Aggregate/deduplicate
pair IDs locally; never paste raw production records.

After at least three clean shadow hours, compare counts by pair class and
incumbent/new verdict, bounds/timing abstentions, latency and error signatures.
Operations alone cannot prove accuracy. Stop at shadow; do not enable on for any
account. A later activation proposal needs refreshed real-end David calibration,
prospective labels including background audio, noisy segmentation, different
devices and clock drift, and a sufficiently precise independent false-fold bound.
No observation window may be shortened. Existing group metadata is retained;
Separate remains available. An image rollback cannot undo folds made while on.
Exact rollback commands and observation timestamps belong in the owner report.

After upstream transcription/attribution fixes, re-export original starts/ends,
re-read David's latest labels, freeze a versioned evaluation snapshot, and rerun
the unchanged matcher. Compare abstention reasons, precision/recall and labeled
background-audio negatives per class. Speaker attribution must remain irrelevant
to the decision. Use capture-component-disjoint held-out labels before tuning;
preserve the old input/label snapshot and re-label cards whose meaning changes;
do not silently loosen cutoffs to recover old noisy positives. Requalify any
threshold/normalization/timing change in shadow before further activation.
