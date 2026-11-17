# Interrupted pendant download recovery

App-only change. No server, wire protocol or firmware behavior changes.

The ring reader commits device/ring/sequence/length coordinates in the phone WAL index transaction, retains downloaded-range receipts across connection epochs, revalidates files and the persisted index, and replays the exact contiguous prefix before choosing a new READ start. Known validated spans inside a read are reused. Unproven gaps stay on the pendant.

Read ownership lasts through STOP, pending disk transactions and final exact-prefix ACK. First-data and DATA-silence deadlines remain; an ordinary coordinator pass can continue while real ring DATA arrives. OS periodic capture fences retain their existing hard limit.

Default-on rollback: build with `--dart-define=OMI_RING_DRAIN_RECOVERY_OFF=true`. This restores the previous session-scoped download proof, read timeout and coordinator deadline behavior. Existing batch proof has its independent `OMI_BATCH_RING_PROOF_OFF` switch.

Server content identity includes the basename and byte hash (`utils/sync/content_id.py`), so old collision-suffixed duplicate files are not guaranteed to collapse. They are preserved; this change prevents future files for exactly proven ranges rather than rewriting upload history.
