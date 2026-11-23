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
  are separate from the Nov 24 sampler.
- Score whole-bundle would-settle and hold outcomes, whole-file coverage and
  agreement on positive proofs. The shadow directly bounds proof work to
  49,920 Firestore point reads, 9,600 GCS RPCs and 7.5 GiB of manifest downloads.
  Report slot-create contenders and transaction-lifecycle RPCs separately.
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
