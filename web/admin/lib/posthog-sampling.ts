/**
 * PostHog ingestion keeps a stable per-distinct-ID sample of some events
 * (contracts/analytics/posthog.json) and tags every kept row with its rate in
 * `omi_sample_pct`. Untagged rows were kept at 100%.
 *
 * Weight each row by SAMPLE_WEIGHT_SQL before aggregating counts or additive
 * measures. For unique users, count each person once at the highest sample
 * rate among that person's eligible rows.
 * Ratios, quantiles and minimum-sample guards stay on the sampled rows.
 * The weight follows any later rate change without a code change.
 */
export const SAMPLE_PCT_SQL =
  "greatest(coalesce(toFloat(properties.omi_sample_pct), 100), 0.01)";
export const SAMPLE_WEIGHT_SQL = `100 / ${SAMPLE_PCT_SQL}`;

/** Earliest UTC day the SCA-3665 config could sample qualified product events.
 * The whole cutover day is considered sampled, including mixed-rate windows. */
export const PRODUCT_SAMPLING_FIRST_DAY = "2026-11-23";
