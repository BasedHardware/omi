/**
 * Formats a date for an `input[type="date"]` value.
 *
 * Uses the local calendar day. `toISOString()` would answer in UTC, so a task
 * due just after midnight shows the day before for users east of UTC, and one
 * due late in the evening shows the next day for users west of it.
 */
export function formatDateInputValue(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}
