/** Approved PostHog ingestion transform: desktop_health_event retained at 10%.
 * Reader/transform contract: docs/posthog-events.md#desktop-health-event-sampling.
 * The orchestrator must confirm this timestamp before enabling the transform.
 */
export const DESKTOP_HEALTH_EVENT_COUNT_MULTIPLIER = 10;
export const DESKTOP_HEALTH_EVENT_SAMPLING_CUTOVER = "2026-10-22T00:00:00Z";

// Weight at event time, before daily aggregation, so a cutover-spanning window
// never rescales historical unsampled events. Apply only to PostHog health rows,
// never chat/floating events or unsampled replacement-aggregate voice rows.
export const DESKTOP_HEALTH_EVENT_WEIGHT_SQL = `if(timestamp >= toDateTime('${DESKTOP_HEALTH_EVENT_SAMPLING_CUTOVER.slice(
  0,
  19
).replace("T", " ")}', 'UTC'), ${DESKTOP_HEALTH_EVENT_COUNT_MULTIPLIER}, 1)`;
