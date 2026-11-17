# External shadow authority transitions

External shadow comparisons run after live authority with independent snapshots.
A live BLOCK followed by an explicitly recorded fresh candidate ALLOW reports
`privacy_decision_mismatch_total{family="external",reason="fresh_authority_change"}`.
Marker changes are diagnostic, not required: a gate can expire without a write.
Both comparison counters still report every disagreement as a mismatch.
The reverse live ALLOW/candidate BLOCK direction retains `stale_block`.
Cached, default, synthesized and unknown candidates retain conservative reasons;
only actual authority-read call sites record fresh provenance. Decisions remain
unchanged.

Regressions cover gate completion, marker restoration, expiry without a write,
legacy/default provenance and actual TTL/Redis/session stale ALLOW detection.
See [comparison evidence](../../privacy-cache-comparisons.md).
