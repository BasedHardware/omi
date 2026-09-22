function pad2(value: number): string {
  return value < 10 ? `0${value}` : `${value}`;
}

/** Local calendar day key for a Date — not UTC, so late-evening items stay put. */
export function dayKeyOf(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

/** Parse a backend `YYYY-MM-DD` day as a local date rather than UTC. */
export function parseLocalDay(dateString: string): Date {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, (month || 1) - 1, day || 1);
}
