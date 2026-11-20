# Recover pusher relay omissions from the original archive

The optional audio app/webhook queue used the custody queue's exception on
saturation. That exception escaped the receiver as an application error. The
socket remained transport-open while background work drained for up to 30
seconds, accepting successful sends that the receiver no longer consumed.
The bounded optional queue now waits for its consumer, with a 300-second
capacity deadline and cancellable ownership of the charged PCM. Genuine
receiver failures close transport before storage/background drain. Storage
and producer fences keep their existing owners and drain paths.

Listen persists existing coalesced playback-recovery debt after each consented
mono original pack commits and before releasing that pack / publishing its
custody receipt. Failure retains the same original for retry. Cold recovery
uses generation-pinned manifests and decoded frame unions for uncovered ranges,
then the existing privacy/CAS audio_files transaction. Overlap is subtracted
by captured sample coordinates; original objects remain immutable. A replay,
reordered receipt or repeated rebuild never adds a second overlapping span.
No STT job or paid work is created by this recovery. Late originals also
invalidate every local raw index, including unframed packs; batch intake's
archive-required inventory is fresh, bounded and still subject to READ consent.
Inventory exclusions have closed reasons instead of silent skips.

The [contract](../../listen_pusher_pipeline.mdx#durable-playback-projection-rebuild-debt)
names proof bounds, counters and kill switch. Decode proof caching never holds
PCM and revalidates the current manifest before reuse. Failed proofs retain
metadata debt and original bytes; no silence, completeness receipt, token clear,
record seal or permission for the phone to delete audio is invented.

Release train order: roll the record-repair consumer image (existing CronJob)
and backend-sync demand reader first, then pusher, then backend-listen. Batch
intake workers (`backend-integration` / their owning CPU image) receive the fresh
listing fix too. Listen and pusher are Release-owned GKE services, not a Cloud
Run backend deploy. No wire change: old/new listen and pusher interoperate.
Old listen does not produce archive-commit debt; new listen with old pusher can
recover from the independently committed original. Roll consumers before new
marker producers so new work never reaches the old metadata-only recovery.
The existing repair job must actually be enabled, unsuspended and provisioned;
this PR does not activate or deploy anything. Stop new handoffs with the existing
default-on PUSHER_PROJECTION_DEBT_DURABLE_ENABLED kill switch on listen/pusher;
stop consumption through the corresponding repair consumer setting. Retain
markers, originals and source WALs when rolling back.

Synthetic tests cover send success without receiver consumption, retry with
identical source identity, lost marker writes and withheld phone ACK, overlapping
and reordered originals, actual Opus frame decoding with real gaps, missing /
ambiguous manifest, wrong generation/hash/owner, proof bounds, consent/privacy,
kill switch, full optional queue and immediate close before drain. Existing
mixed-peer / uncertain-send, cancellation, projection deletion and CAS suites
remain required. Local tests are not deployed recovery or installed-phone proof.
Existing-account repair remains a separate bounded owner-authorized action.
