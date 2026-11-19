# Reduced 2026-11-04 parity replay

Synthetic artifacts in the existing pullers' formats, using aggregate figures from
`omi-workspace/data/run-2026-11-08-spend-ledger/reconcile-REPORT.md` §2 and
`plan.md` §0/§3 (read 2026-11-08). No account captures, identifiers or secrets.

The GCP non-Vertex remainder is collapsed into one synthetic Compute Engine SKU;
this is a total-preservation fixture, not an observed service distribution. PT
uses the report's $299.58 unit-cost split, not a newly measured billing SKU.
Two synthetic SaaS/infra charges per vendor avoid the one-off annual heuristic and replay their reported daily run rates
through the real Mercury calculation (30.4375 divisor). Other covered cash days
are synthetic zeros. Anthropic is a successful zero-report example; its live
org spend was not re-fetched. Stripe repeats the one-day aggregate over seven
days to exercise the effective-rate formula; ~$108.70 is a fixture calculation,
not a measured historical seven-day subscription fee estimate.

Expected components: GCP ex-Vertex $1680.85; Vertex + Gemini $328.68; OpenAI
$295.68; Soniox $8.2477; Modulate cash $200; SaaS $750.50; Stripe $281.84;
infra $3.41. Their sum is **$3549.2077**. The plan's $3543 headline used the
screenshot's rounded/older OpenAI $290, not the ledger's $295.68. The parity
checker uses the explicit component sum ($3549.21 +/- $2), with each component
within $1. Modulate modelled must have zero rows, never a zero-dollar row.
