# Forward canonical audio (review proposal; not applied)

David's 2026-10-15 ruling: retain capture audio indefinitely except authorized
privacy deletion. No scanning, migration, rewriting, repacking or reclassification
of existing stock. Existing prod/dev lifecycle JSON is unchanged.

`canonical-forward.json` and `cache-forward.json` are contracts for **new empty
regional buckets only**. Do not send them to the existing private-cloud or syncing
buckets. Region us-central1 follows backend compute; residency/resilience approval
is required before provisioning. Metadata indexes remain Standard indefinitely.
Sources remain Standard until a verified pack has replaced them; no source TTL.

Apply runbook (separate reviewed operator change; this PR does not apply it):

1. Allocate two never-used bucket names. Describe must return NotFound, not 403.
   Create in us-central1, Standard, uniform bucket-level access and public access
   prevention enforced. Set versioning disabled and soft-delete duration zero
   **at creation**, before granting writer access. No retention lock or Autoclass.
2. Verify both buckets are empty and have no existing generations/soft-deleted
   objects, no notifications, and correct location/policies. Stop on uncertainty.
3. Extract each JSON's `lifecycle` value to an apply file and install it on its
   corresponding new bucket. Re-describe and compare rules verbatim. Never alter
   existing lifecycle policies or use the legacy workflow's prod bucket target.
4. Set `BUCKET_CANONICAL_AUDIO` to the new archive bucket on every pusher/sync and
   account-deletion host. Grant only necessary object rights to those runtimes.
   `AUDIO_CANONICAL_PACKING_ENABLED=false` is the default. Enable only after dev
   capture, deletion, crash-resume and latency qualification. Index and sources
   use release-specific prefixes; no writer can opt legacy objects into packing.
5. An operator job can run `PYTHONPATH=. .venv/bin/python
   scripts/pack_canonical_audio.py --owner UID --day YYYY-MM-DD` from backend.
   Closed UTC days only. One owner at a time; account operation gate serializes
   packing and conversation rewrite with deletion/legal holds. Keep each run below
   the gate staleness timeout; monitor/recover failed intents before scheduling.
   No scheduler resources are applied or automatically enabled by this PR.
6. Cache/staging contract is for future producers using its release prefixes in
   the second new bucket. Current playback/staging producers keep their existing
   routes/policies. Deploy their routing separately before claiming cache savings.
7. Rollback stops the packer flag, never deletes packs or removes deletion config.
   Existing pack/index deletion remains active with flag off. Source/receipt and
   pending index prefixes are included in account wipe verification.

Raw mobile packets use the as-captured uint32le length-prefixed Opus stream (or
its unchanged encryption envelope). Desktop/pendant pusher intake today supplies
PCM16; it is labeled PCM, with supplied sample rate and plaintext hash, never
claimed to be original Opus. No legacy chunks are packed. Training consumers use
owner manifests; serving playback continues to use existing renditions. Mobile
capture has no conversation ID at admission; its provenance preserves the filename
and account deletion erases it. Linked capture entries can be removed by
conversation ID, rewriting the affected pack without mixing owners.

## List-price check (USD; 2026-10-15)

[Google Cloud Storage pricing](https://cloud.google.com/storage/pricing), flat
namespace us-central1: Standard $0.020, Coldline $0.004, Archive $0.0012 per
GiB-month (730 hours). A 256 MiB / 0.25 GiB shard saves $0.004/month when moved
Standard→Coldline and another $0.0007/month Coldline→Archive. Lifecycle transitions
are destination Class A operations: $0.020/1000 = **$0.000020 per pack** to Coldline;
$0.050/1000 = **$0.000050 per pack** to Archive. Break-even is about 0.15 and 2.14
days respectively at 30 days/month. Tiny 4 KiB manifests do not transition: the
operation fee would exceed their savings. 256 decimal MB instead saves $0.003815
and $0.000668/month. Tar padding and metadata add a small overhead.

Coldline/Archive reads cost $0.02/$0.05 per GiB plus operations/network; user
privacy rewrites/deletes may incur minimum-duration charges (90/365 days).
Lifecycle class transitions themselves are exempt from early deletion charges.
Packing does not avoid original intake PUTs and adds source GET, pack PUT, index
operations and temporary duplicate bytes. No savings from existing stock claimed.
