"""PAPER — build a finite daily edition from ambient context.

Five sections, every one fed by a live source: what the reader did yesterday
(conversations, screen, daily summary), what is on them today (calendar, action
items), their newsletters deduped to one line per story (Gmail), external
material ranked against interests learned from their own record (arXiv, web),
and one drawn moment.

The split that keeps this honest: sources and aggregation are deterministic and
testable, and the model is used only where prose is genuinely needed. Every
section is optional, every source reports its own health, and nothing is padded
when a day is quiet — see docs/product/paper/SPEC.md.
"""
