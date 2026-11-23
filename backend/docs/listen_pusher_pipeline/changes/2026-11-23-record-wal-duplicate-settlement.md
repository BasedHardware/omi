# Native WAL duplicate settlement

SCA-3376 phase 2a reuses the canonical completed native record when every file
in the upload has a uniquely positioned, byte-exact Opus packet run already
held in its original live archive and included in its admitted source slices.
The initial implementation accepts the 16 kHz mono coordinate convention and
single-target, completed obligations only. Historical intakes without the
source-slice attestation, partial captures, unsupported framing, conflicting
positions, trim uncertainty and incomplete inventories hold. A mixed bundle
cannot settle in part. No raw-live media body is fetched. No provider task is
created and no server source bytes are removed.

The native writer adds the attestation to its existing intake write. Settlement
reads owner/privacy/erasure authority, the closed barrier, attestation and
canonical status, then validates pinned GCS media and manifest metadata before a
bounded CAS. Exact retries reuse the same alias and canonical handle through a
read-only path, including with the settlement flag off. Rebundles prove every
file again before writing the new alias and reuse matching per-file receipts.
Retain receipt readers on rollback. Merge cleanup marks the source row before
removing backing audio, and retained-donor erasure requires its tombstone. A
failed fence leaves prefix cleanup pending. A canonical revision change refuses replay
until equivalence is established.
Expected optional proof failures continue through the existing upload coverage
path, including during the final snapshot's reads and revalidation. Fallback
closes the commit fence before the worker can dispatch. Once the commit RPC
has begun, an uncertain result holds for exact replay.
The legacy coverage transaction preserves a concurrent settlement receipt and
leaves its status to exact replay.

## Terminal status retention

Settlement copies the already-authorized completed status into one compact
receipt per canonical handle, in the existing intake collection. The alias,
file receipts and status receipt share a 45-day absolute deadline. A later
distinct alias can advance the shared status and matching file deadlines only
after full canonical proof. Exact replay and direct polls never extend them.
Existing canonical content, job and media retention keep their original clocks.
Both readers check live privacy and the original source binding, including the
successor when present. The intake receipt is erased with its original owner or
conversation. Ordinary TTL lag confers no replay authority.

An active proof may issue one additional point read and one status-receipt
write at commit, for a maximum of 105 proof reads across both views and
22 receipt writes plus the first-settlement donor write. Shadow remains
bounded to 104 reads per candidate with no witness writes. Direct polls for
eligible batch handles add one document read on a miss, and use at most 11
document reads on a hit including the owner snapshot.
The bounded authority snapshot uses the live privacy walk directly.
Privacy experiment observations run outside these proof and replay views.
Report fixed-label lookup hit, miss and error counts and include them in
Release's read budget before activation.

## Non-erasure merges

Durable manual merge admission persists the keep-or-remove choice alongside
its source claims. The claimed donor row blocks new settlement and keeps the
original replay authorized until publication. The correction-transfer
transaction validates the current merge lease and both ends of the erase
lineage, publishes a reciprocal direct link, and advances to source cleanup
together. A successor merging again republishes the flattened lineage in that
transaction. This bounds a successor to 16 retained original donors. A merge
above the bound defers before retraction. Exact replay allows one redirect
and up to 56 point reads. Explicit deletion of either record defeats replay;
successor deletion uses its existing persisted source-deletion lineage.
Admission defers a retained-donor merge before claiming sources if any input
uses custom speech recognition.

Post-publication donor cleanup retracts derived state and preserves original
custody, canonical obligations and aliases. Smart merge, automatic sync
lineage and v3 projection defer when they cannot maintain these bindings. V3
full-row replacement, including refinement, re-derive and backfill, defers on
settled source rows even before a merge, as well as retained-lineage rows.
Before activation, Release must account for those deferrals in the serving cohort.
A rollback after the first settlement must keep the verified merge writers,
erasure and replay behavior serving, including with settlement disabled.

## Release gates

- Keep all controls off for the initial carrier. Qualify both effective
  `raw-live/` and `audio-outbox/` lifecycles in `omi-private-cloud-sync`.
  Verify that every positive-traffic and ready source writer, privacy purge and
  merge/removal writer serializes with the Firestore conflict set. A writer
  capable of deleting these objects after a failed fence leaves the cohort
  unqualified. A conditional object HEAD alone does not exclude erasure.
- Keep phase 1 broad admission off. With a separate exact written privacy
  approval and Release go-ahead and inverse, set
  `RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED=true` and the one approved
  `RECORD_WAL_DUPLICATE_SHADOW_EPOCH` on backend-sync. Shadow preserves the
  existing reply and writes no settlement receipts. Its own 480 durable slots
  are separate from the Nov 24 sampler. Only requests with a nonempty capture
  claim set and one claim per staged file can claim a shadow slot.
- Score whole-bundle would-settle and hold outcomes, whole-file coverage and
  agreement on positive proofs. The shadow directly bounds proof work to
  49,920 Firestore point reads, 9,600 GCS RPCs and 7.5 GiB of manifest downloads.
  Report slot-create contenders separately. The fixed-label Firestore
  lifecycle counter records begin, commit and rollback attempts and outcomes
  at the worker making the call, including deadline and RPC cancellation.
  An expired unattempted rollback is a separate outcome. The shadow runs at
  most two read-only views per claim, so it can attempt at most 1,920
  lifecycle RPCs over the window (two begins and two rollbacks per claim).
  It should never attempt a commit.
  Reconcile early alias reads, reached candidates, holds and replays before
  setting active budget and guard thresholds. No activation on absent metrics.
- After full custody review and written Release approval, clear the shadow
  epoch and ramp `RECORD_WAL_DUPLICATE_PERCENT` at 1, 10, 50 and 100 on
  backend-sync. The stable cohort key is the owner. Release owns expansion,
  one closed matched guard window per step, and rollback. Shadow and active
  settings are mutually exclusive. Zero or unset stops new settlements,
  with no change to the committed alias reader.
- Post closed matched 24-hour sync status-code counts, 503/(200+202), peak
  instances and settled bundle/file/byte counts. This phase uses no paid
  gap-recovery budget.
