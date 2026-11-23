/**
 * PostHog ingestion keeps a stable per-distinct-ID sample of some events
 * (contracts/analytics/posthog.json) and tags every kept row with its rate in
 * `omi_sample_pct`. Untagged rows were kept at 100%.
 *
 * Weight each row by SAMPLE_WEIGHT_SQL before aggregating counts or additive
 * measures. For unique users, divide by the largest rate seen
 * (`uniq * 100 / max(SAMPLE_PCT_SQL)`), as the Device Signals rules do.
 * Ratios, quantiles and minimum-sample guards stay on the sampled rows.
 * The weight follows any later rate change without a code change.
 */
export const SAMPLE_PCT_SQL =
  "greatest(coalesce(toFloat(properties.omi_sample_pct), 100), 0.01)";
export const SAMPLE_WEIGHT_SQL = `100 / ${SAMPLE_PCT_SQL}`;
