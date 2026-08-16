const DAY_MS = 86_400_000;

export interface DailyNewUsersPoint {
  date: string;
  users: number;
}

export interface WeeklyNewUsersPoint {
  week: string;
  users: number;
}

export interface DailyActivationPoint {
  date: string;
  signups: number;
  activated: number;
}

export interface WeeklyActivationPoint {
  week: string;
  signups: number;
  activated: number;
  rate: number;
}

function utcDate(value: string | Date): Date | null {
  const date =
    value instanceof Date
      ? new Date(value.getTime())
      : new Date(`${value.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function mondayKey(value: string | Date): string | null {
  const date = utcDate(value);
  if (!date) return null;
  date.setUTCHours(0, 0, 0, 0);
  const daysSinceMonday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - daysSinceMonday);
  return date.toISOString().slice(0, 10);
}

export function completedWeeklyNewUsers(
  points: readonly DailyNewUsersPoint[],
  today = new Date(),
): WeeklyNewUsersPoint[] {
  const currentWeek = mondayKey(today);
  if (!currentWeek) return [];

  const totals = new Map<string, number>();
  for (const point of points) {
    const week = mondayKey(point.date);
    if (!week || week >= currentWeek || !Number.isFinite(point.users)) continue;
    totals.set(week, (totals.get(week) ?? 0) + point.users);
  }

  return Array.from(totals, ([week, users]) => ({ week, users })).sort((a, b) =>
    a.week.localeCompare(b.week),
  );
}

export function maturedWeeklyActivation(
  points: readonly DailyActivationPoint[],
  today = new Date(),
  maturityDays = 7,
): WeeklyActivationPoint[] {
  const todayUtc = utcDate(today);
  if (!todayUtc) return [];
  todayUtc.setUTCHours(0, 0, 0, 0);

  const totals = new Map<string, { signups: number; activated: number }>();
  for (const point of points) {
    const week = mondayKey(point.date);
    if (
      !week ||
      !Number.isFinite(point.signups) ||
      !Number.isFinite(point.activated)
    ) {
      continue;
    }
    const current = totals.get(week) ?? { signups: 0, activated: 0 };
    current.signups += point.signups;
    current.activated += point.activated;
    totals.set(week, current);
  }

  return Array.from(totals, ([week, totalsForWeek]) => {
    const weekStart = utcDate(week)!;
    const fullyMatureAt = new Date(
      weekStart.getTime() + (7 + maturityDays) * DAY_MS,
    );
    return {
      week,
      fullyMatureAt,
      ...totalsForWeek,
    };
  })
    .filter((point) => point.fullyMatureAt <= todayUtc)
    .sort((a, b) => a.week.localeCompare(b.week))
    .map(({ week, signups, activated }) => ({
      week,
      signups,
      activated,
      rate: signups > 0 ? Math.round((activated / signups) * 1000) / 10 : 0,
    }));
}
