"""PAPER — build a finite daily edition from ambient context.

Most of an edition is computed, not generated. Open loops, dropped people and stance
one-sidedness are deterministic functions of stored daily summaries; only the lede prose
and the counterpoint argument need a model. That split keeps the paper testable and makes
the "never fabricate" rule enforceable — see docs/product/paper/SPEC.md.
"""
