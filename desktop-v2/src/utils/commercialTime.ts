/**
 * Commercial time gating — restricts certain captures (screen recording, audio)
 * to weekday working hours.
 *
 * Default: Monday–Friday, 09:00–17:00, local time.
 *
 * Used by rewindStore and audioStore to pause capture outside business hours
 * and resume it when the window re-opens.
 */

export interface CommercialHours {
  /** Days of the week allowed. 0 = Sunday, 1 = Monday, ..., 6 = Saturday. */
  daysOfWeek: number[];
  /** Start hour (0-23), local time. */
  startHour: number;
  /** End hour (0-23), local time — exclusive (i.e. 17 means stop at 17:00). */
  endHour: number;
}

export const DEFAULT_COMMERCIAL_HOURS: CommercialHours = {
  daysOfWeek: [1, 2, 3, 4, 5], // Mon-Fri
  startHour: 9,
  endHour: 17,
};

/** Return true if `now` falls inside the given commercial window. */
export function isCommercialTime(
  now: Date = new Date(),
  hours: CommercialHours = DEFAULT_COMMERCIAL_HOURS,
): boolean {
  const dow = now.getDay();
  if (!hours.daysOfWeek.includes(dow)) return false;
  const h = now.getHours();
  return h >= hours.startHour && h < hours.endHour;
}

/**
 * Subscribe to commercial-time status changes.
 *
 * The callback is fired once immediately with the current state, and again
 * every time the status flips (on a 30-second poll).
 *
 * Returns an unsubscribe function.
 */
export function watchCommercialTime(
  onChange: (isOpen: boolean) => void,
  hours: CommercialHours = DEFAULT_COMMERCIAL_HOURS,
): () => void {
  let lastState = isCommercialTime(new Date(), hours);
  onChange(lastState);

  const id = setInterval(() => {
    const current = isCommercialTime(new Date(), hours);
    if (current !== lastState) {
      lastState = current;
      onChange(current);
    }
  }, 30_000);

  return () => clearInterval(id);
}
