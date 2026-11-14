# Preserve colliding phone WAL uploads

Released clients retain same-time audio under `_<timestamp>_uN.bin`. Parse
the timestamp before a single ASCII `u` plus decimal digits, through the same
capture-clock checks. Malformed suffixes and implausible future clocks still
fail with the existing typed refusal.

Correction after custody review: the HTTP path already normalized all nonempty
collision uploads before timestamp parsing, since `7b1a45549b3c` (2026-11-01).
The original diagnosis did not describe that main upload path. Removing its
normalizer changed existing ledger identities and was unsafe for retries and
artifact repair. Restore the exact legacy normalizer and signed-manifest mapping
unconditionally: both new and old revisions now stage and hash the same names,
including during rollback. No ledger migration or alternate owner is created.
Unrenamable alias bundles keep the legacy refusal. The parser extension serves
direct/internal readers; no audio custody rule changes.

The [sync contract](../../listen_pusher_pipeline.mdx) defines the default-on
`SYNC_COLLISION_SUFFIX_ENABLED` kill switch. Off restores direct admission
parsing; HTTP uploads keep their pre-Q12 normalization and identity. Internal
reads continue draining already staged work. Tests cover
suffix grammar, early/future policy, separate storage/content keys, raw manifest
names, old-owner retry/repair, new-to-old identity, batch decoding and coverage
derivatives. Production behavior and phone
retry timing are not verified by these hermetic tests.
