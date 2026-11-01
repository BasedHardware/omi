-- Stripe-book MRR snapshot, the ARPMAU numerator (spec §1 / workstream W2).
-- Read-only. Do not write this table.
--
-- Source: `based-hardware.omi_finops.plan_revenue_daily`.
-- `mrr_usd` is the finops Stripe snapshot for paying subscriptions on
-- `snapshot_date` (trials are counted in `trialing_subs` and are not in
-- `mrr_usd`). `pull_stripe.py` applies the subscription coupon before it
-- writes this column. Webhook `mrr_cents` is a USD list price and is not
-- this number.
--
-- Join rule
--   A HogQL week is the UTC Monday `week_start` with exclusive end
--   `week_end = week_start + 7 days`.
--   MRR for that week is SUM(mrr_usd) on the latest `snapshot_date` that is
--   <= week_end. If no snapshot is that old, MRR is unknown, not zero.
--   MAU is the HogQL trailing-30-day count ending at that same week_end
--   (`contracts/product-telemetry/posthog/subscription-baseline.hogql`).
--   ARPMAU = MRR / MAU. NULL when either side is missing or MAU is 0.
--
-- This statement returns one row: the latest snapshot, which is the numerator
-- for the latest week whose exclusive end is on or after that snapshot date.

SELECT
  snapshot_date,
  SUM(mrr_usd) AS mrr_usd,
  SUM(paying_subs) AS paying_subs,
  SUM(trialing_subs) AS trialing_subs
FROM `based-hardware.omi_finops.plan_revenue_daily`
WHERE snapshot_date = (
  SELECT MAX(snapshot_date)
  FROM `based-hardware.omi_finops.plan_revenue_daily`
)
GROUP BY snapshot_date
