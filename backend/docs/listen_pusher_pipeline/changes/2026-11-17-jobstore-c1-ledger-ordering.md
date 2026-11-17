# C1 observer and purge ordering

The pipeline ledger observes a committed capture transition. It never grants
admission, custody, a paid retry or customer visibility. Its failure stays
fail-open for the real transition. A delayed observer must independently pass
the current privacy fences in the transaction that commits its ledger write.

`pipeline_ledger.advance` reads the account deletion marker and every bound
source conversation, then performs `assert_batch_write_allowed`, inside the
same Firestore transaction as its ledger CAS. Retried callbacks clear their
pending transition observations first. A committed account tombstone, closed
privacy generation or deleted source therefore prevents a late observer from
recreating a purged ledger row. Source references follow the original capture;
they do not become new authority or extend the capture's lifetime.

Account/conversation erasure closes the corresponding authority and drains
in-flight effects before destructive copy retirement. The ledger purge follows
that close; removing a ledger document alone is not a deletion fence. A racing
observer either commits before the close and is covered by the purge, or its
transaction conflicts/retries and refuses after the close. The existing
pipeline-ledger integration tests exercise the actual transaction interceptor,
including P24 late observers and deletion during a callback retry.

D's retained-copy census still owns every unresolved source, cold object,
handoff, journal and receipt until its original retirement conditions are
proved. Ledger deletion is neither final erasure evidence nor permission to
delete those copies. Production G2 scheduling, all-writer/remote/reverse and
full process-crash qualification remain readiness gates.
