/** Approved PostHog ingestion transform: desktop_health_event retained at 10%.
 * Reader/transform contract: docs/posthog-events.md#desktop-health-event-sampling.
 * Armed 2026-10-17: the transform (hog function 01a13f9f…, cost cut) began
 * sampling desktop_health_event at 03:43:08Z, which is the cutover below.
 */
export const DESKTOP_HEALTH_EVENT_COUNT_MULTIPLIER = 10;
export const DESKTOP_HEALTH_EVENT_SAMPLING_CUTOVER: string | null =
  "2026-10-17T03:43:08Z";

// Weight at event time, before daily aggregation, so a cutover-spanning window
// never rescales historical unsampled events. Apply only to PostHog health rows,
// never chat/floating events or unsampled replacement-aggregate voice rows.
export function desktopHealthEventWeightSql(cutover: string | null) {
  if (cutover == null) return "1";
  // Only a canonical UTC deployment constant is accepted, never SQL input.
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(cutover) ||
    !Number.isFinite(Date.parse(cutover))
  )
    throw new Error("Invalid desktop health sampling cutover");
  return `if(timestamp >= toDateTime('${cutover
    .slice(0, 19)
    .replace("T", " ")}', 'UTC'), ${DESKTOP_HEALTH_EVENT_COUNT_MULTIPLIER}, 1)`;
}
export const DESKTOP_HEALTH_EVENT_WEIGHT_SQL = desktopHealthEventWeightSql(
  DESKTOP_HEALTH_EVENT_SAMPLING_CUTOVER
);
