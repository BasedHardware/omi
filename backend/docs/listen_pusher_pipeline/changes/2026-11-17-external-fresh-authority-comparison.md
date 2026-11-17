# External shadow authority transitions

External shadow comparisons run after live authority with independent snapshots.
A fresh candidate whose common marker observation changed now reports
`privacy_decision_mismatch_total{family="external",reason="fresh_authority_change"}`.
Both comparison counters still report the disagreement as a mismatch. Cached
candidates retain `stale_allow`/`stale_block`, and decisions remain unchanged.

The regression covers a destructive gate finishing or account marker restoring
access after both token observations, preserving the original live BLOCK.
See [comparison evidence](../../privacy-cache-comparisons.md).
