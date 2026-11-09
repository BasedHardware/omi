# Per-object DEKs for transcript lake writes

New object-lake writes use envelope v2: `>4sBI12s40s` contains `OLK1`, version
`2`, the space-key version, a 12-byte nonce and a 40-byte AES-KW wrap of a fresh
random 32-byte object DEK. AES-GCM uses each object DEK once, with the full object
path as AAD and the existing zlib compression. AES-KW has no nonce; wrapping is
local and adds no KMS calls. Key wraps live in immutable object bytes, never in
mutable GCS metadata. Readers retain legacy v1 support and fail closed on unknown
versions, truncation, wrap tampering or authentication failure.

The [transcript pointer contract](../../listen_pusher_pipeline.mdx) and codec seam
are unchanged: pointer `dek_version` names the space key in either envelope.
Create-only retries retain the first payload. Space-key rotation affects new
objects only; retired versions remain readable, with no eager or lazy re-wrap.
Destroying the space-key authority shreds both formats even with a warm cache.
Upload and deletion fences are unchanged. C4 must cover v2 objects in its
prefix-purge / keys-last account-wipe test.

Dev write admission now permits real bucket and KMS bindings. Production
deployment validation still refuses enabled writes or positive percentages until
the C4 wipe-coverage gate is green. No environment values change in this PR:
`OBJECT_LAKE_WRITE_ENABLED` remains default-off, `OBJECT_LAKE_WRITE_PERCENT`
defaults to `0`, and read admission is unchanged. A future dev ramp can enroll a
small cohort; production enablement belongs to C4.

Hermetic tests exercise both envelope formats, independent object keys even with
equal nonces, wrap corruption and swaps, rotation without rewriting, cached-key
shredding, KMS-call counts, deployment admission, and codec/upload-fence regressions.
