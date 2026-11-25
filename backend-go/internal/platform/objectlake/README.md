# Offloaded transcript reads

A finalization adapter can pass the Firestore pointer from its guarded conversation snapshot to
`Reader.Read(ctx, guard, owner, conversation, pointer)`. Call after the Firestore transaction
returns and while the guard is live. On `ErrChanged`, reload the conversation snapshot.
The adapter still owns the source revision check when saving its result.

The binary supplies the data-plane docstore, Storage and Cloud KMS clients, and Python's
`BUCKET_OBJECT_LAKE`, `OBJECT_LAKE_KMS_KEY` and `OBJECT_LAKE_READ_ENABLED` settings.
Python enables reads by default independently of its write rollout.

The reader checks the owner deletion marker, conversation and versioned space key together.
It accepts an offloaded transcript only while the row is shared or public, unlocked, and
eligible for finalization. It authenticates the object path, key version, length and plaintext
digest. It checks authority again before returning speech or reporting an absent object.
A retired version remains readable while its wrapped key is present. Reads never create a key.

The result is the owner's ordered finalization transcript, with storage-only identity fields
removed. The training consent stamp belongs to Python's upload and training paths.
This API grants no training or identity-hydration permission and retains no plaintext cache.

| Result | Meaning |
| --- | --- |
| Successful empty slice | The authenticated payload decoded to an empty list. |
| ErrAbsent | Storage returned 404 while the reference and key authority were still current. |
| ErrShredded | The space key is missing or destroyed, or KMS reports a disabled or destroyed version. |
| ErrCorrupt | The reference, envelope, decoded content or requested version in a live key record is invalid. |
| ErrUnavailable | The read switch, service availability, configuration or malformed custody record prevented resolution. |
| ErrChanged, ErrRestricted, docstore or guard error | Reload or apply the caller's existing guard, erasure and finalization rules. |

The package tests use Python-sealed synthetic vectors, a private Firestore emulator project
and local HTTP endpoints for the KMS and Storage clients.
