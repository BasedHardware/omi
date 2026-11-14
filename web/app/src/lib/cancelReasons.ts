/**
 * Closed cancel-reason vocabulary shared with mobile
 * (contracts/analytics/events.json). No free-string reasons reach analytics.
 */
export const CANCEL_REASONS = [
  'too_expensive',
  'not_using_enough',
  'missing_features',
  'audio_quality',
  'battery_drain',
  'found_alternative',
  'other',
] as const;

export type CancelReason = (typeof CANCEL_REASONS)[number];

const CANCEL_REASON_SET: ReadonlySet<string> = new Set(CANCEL_REASONS);

export function cancelReasonWire(
  raw: string | null | undefined,
): CancelReason | 'none' | 'unknown' {
  const value = raw?.trim() ?? '';
  if (value === 'none') return 'none';
  return CANCEL_REASON_SET.has(value) ? (value as CancelReason) : 'unknown';
}
