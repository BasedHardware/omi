// Day and time labels for mobile lists, matching the shipping phone app:
// day headers read "Today", "Yesterday", "Wed, Sep 23", and rows under a day
// header show only the time.

function startOfLocalDay(epochMs: number): number {
  const date = new Date(epochMs);
  return new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  ).getTime();
}

function dayOffset(epochMs: number, nowMs: number): number {
  return Math.round(
    (startOfLocalDay(nowMs) - startOfLocalDay(epochMs)) / 86_400_000,
  );
}

/** Stable key for grouping by local calendar day. */
export function mobileDayKey(epochMs: number): string {
  const date = new Date(epochMs);
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/** "Today", "Yesterday", "Wed, Sep 23" (the year is added when it differs). */
export function mobileDayLabel(epochMs: number, nowMs: number): string {
  if (!Number.isFinite(epochMs)) {
    return 'Undated';
  }
  const offset = dayOffset(epochMs, nowMs);
  if (offset === 0) {
    return 'Today';
  }
  if (offset === 1) {
    return 'Yesterday';
  }
  const sameYear =
    new Date(epochMs).getFullYear() === new Date(nowMs).getFullYear();
  return new Date(epochMs).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : {year: 'numeric'}),
  });
}

/** "5:00 PM" in the device locale. */
export function mobileTimeLabel(epochMs: number): string {
  if (!Number.isFinite(epochMs)) {
    return '';
  }
  return new Date(epochMs).toLocaleTimeString(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  });
}

/** Compact when-label for a row without a day header: time today, else the day. */
export function mobileWhenLabel(epochMs: number, nowMs: number): string {
  if (!Number.isFinite(epochMs)) {
    return '';
  }
  const offset = dayOffset(epochMs, nowMs);
  if (offset === 0) {
    return mobileTimeLabel(epochMs);
  }
  if (offset === 1) {
    return 'Yesterday';
  }
  const sameYear =
    new Date(epochMs).getFullYear() === new Date(nowMs).getFullYear();
  return new Date(epochMs).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : {year: 'numeric'}),
  });
}

export function epochOf(value: string | number | null | undefined): number {
  if (value === null || value === undefined) {
    return Number.NaN;
  }
  return typeof value === 'number' ? value : Date.parse(value);
}
