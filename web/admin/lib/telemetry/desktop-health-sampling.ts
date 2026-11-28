/** desktop_health_event is sampled at ingestion (contracts/analytics/posthog.json).
 * Reader/transform contract: docs/posthog-events.md#ingestion-sampling.
 * Every kept row since the 2026-10-17T03:43:08Z cutover carries omi_sample_pct
 * (10 until SCA-3665); earlier rows are untagged and weigh one. Weight at event
 * time, before daily aggregation. Apply only to PostHog health rows, never
 * chat/floating events or unsampled replacement-aggregate voice rows.
 */
export { SAMPLE_WEIGHT_SQL as DESKTOP_HEALTH_EVENT_WEIGHT_SQL } from "../posthog-sampling";
