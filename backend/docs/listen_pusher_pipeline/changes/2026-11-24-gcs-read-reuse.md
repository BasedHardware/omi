# Reuse verified GCS reads within audio operations

SCA-4225 uses exact custody-manifest keys after verified discovery and
reuses whole verified packs across playback parts and retained batch slices.
Batch reads use conditional source metadata and reuse the lookup metadata
when recovering a staging result. Custody acknowledgement and playback
publication retain their live checks.

The [readback runbook](../../runbooks/private-sync-inventory-manifest-reuse.md#sca-4225-operation-local-reads)
lists the default-on switches, counters, and rollback. The
[private-sync lifecycle policy](../../../deploy/storage-lifecycle/README.md)
records the separately dispatched Coldline size floor and its rollback.
