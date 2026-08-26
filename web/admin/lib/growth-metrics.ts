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
  /**
   * Subset of `signups` running a desktop build that is able to emit the
   * `Memory Created` event the numerator counts. Signups on older builds cannot
   * activate no matter what the user does, so pooling them silently deflates the
   * rate during a rollout.
   */
  capableSignups?: number;
  capableActivated?: number;
}

export interface WeeklyActivationPoint {
  week: string;
  signups: number;
  activated: number;
  /** Pooled rate over every signup, including those that cannot report. */
  rate: number;
  /**
   * Rate over signups whose build can report activation, and null when none
   * could. This is the honest read: a week nobody could report is a blind spot,
   * not a week of zero activation.
   */
  capableRate: number | null;
  telemetryCoverage: number | null;
}

export interface ActivationSummary {
  /** Signups whose 7-day activation window has fully elapsed. */
  signups: number;
  activated: number;
  rate: number | null;
  /** Same, restricted to signups whose build can report activation at all. */
  capableSignups: number;
  capableActivated: number;
  capableRate: number | null;
  /**
   * Percentage of matured signups on a reporting-capable build. Below 100 means
   * the headline `rate` is diluted by users who physically cannot report, not by
   * users failing to activate.
   */
  telemetryCoverage: number | null;
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

  const totals = new Map<
    string,
    {
      signups: number;
      activated: number;
      capableSignups: number;
      capableActivated: number;
    }
  >();
  for (const point of points) {
    const week = mondayKey(point.date);
    if (
      !week ||
      !Number.isFinite(point.signups) ||
      !Number.isFinite(point.activated)
    ) {
      continue;
    }
    const current = totals.get(week) ?? {
      signups: 0,
      activated: 0,
      capableSignups: 0,
      capableActivated: 0,
    };
    current.signups += point.signups;
    current.activated += point.activated;
    // A series recorded before capability was tracked carries no capable
    // counts; treat those days as fully capable rather than as zero coverage.
    current.capableSignups += point.capableSignups ?? point.signups;
    current.capableActivated += point.capableActivated ?? point.activated;
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
    .map(({ week, signups, activated, capableSignups, capableActivated }) => ({
      week,
      signups,
      activated,
      rate: signups > 0 ? Math.round((activated / signups) * 1000) / 10 : 0,
      capableRate: percent(capableActivated, capableSignups),
      telemetryCoverage: percent(capableSignups, signups),
    }));
}

function percent(numerator: number, denominator: number): number | null {
  if (denominator <= 0) return null;
  return Math.round((numerator / denominator) * 1000) / 10;
}

export interface ActivationCohortMember {
  signupAt: string;
  activated: boolean;
}

export interface ActivationSeries {
  weeks: { week: string; signups: number; activated: number; rate: number }[];
  signups: number;
  activated: number;
  rate: number | null;
}

/**
 * Roll a per-user activation cohort into weekly buckets plus a pooled rate.
 *
 * Unlike the PostHog series this has no telemetry-coverage dimension: it is
 * derived from the conversation records themselves, which exist regardless of
 * what the client managed to report. Callers must pass only members whose
 * activation window has already elapsed.
 */
export function rollUpActivationCohort(
  members: readonly ActivationCohortMember[],
): ActivationSeries {
  const totals = new Map<string, { signups: number; activated: number }>();
  let signups = 0;
  let activated = 0;

  for (const member of members) {
    const week = mondayKey(member.signupAt);
    if (!week) continue;
    const current = totals.get(week) ?? { signups: 0, activated: 0 };
    current.signups += 1;
    signups += 1;
    if (member.activated) {
      current.activated += 1;
      activated += 1;
    }
    totals.set(week, current);
  }

  const weeks = Array.from(totals, ([week, t]) => ({
    week,
    signups: t.signups,
    activated: t.activated,
    rate: percent(t.activated, t.signups) ?? 0,
  })).sort((a, b) => a.week.localeCompare(b.week));

  return { weeks, signups, activated, rate: percent(activated, signups) };
}

/**
 * Pool a daily activation series into the single headline rate.
 *
 * Only signup days whose activation window has fully elapsed are counted. A
 * signup from yesterday has not had its 7 days yet, so including it would count
 * a guaranteed-zero numerator against a real denominator and drag the rate down
 * every single day.
 */
export function summarizeActivation(
  points: readonly DailyActivationPoint[],
  today = new Date(),
  maturityDays = 7,
): ActivationSummary {
  const todayUtc = utcDate(today);
  const empty: ActivationSummary = {
    signups: 0,
    activated: 0,
    rate: null,
    capableSignups: 0,
    capableActivated: 0,
    capableRate: null,
    telemetryCoverage: null,
  };
  if (!todayUtc) return empty;
  todayUtc.setUTCHours(0, 0, 0, 0);

  const totals = { ...empty };
  for (const point of points) {
    const day = utcDate(point.date);
    if (
      !day ||
      !Number.isFinite(point.signups) ||
      !Number.isFinite(point.activated)
    ) {
      continue;
    }
    if (new Date(day.getTime() + maturityDays * DAY_MS) > todayUtc) continue;

    totals.signups += point.signups;
    totals.activated += point.activated;
    // A series recorded before capability was tracked carries no capable
    // counts; treat those days as fully capable rather than as zero coverage.
    totals.capableSignups += point.capableSignups ?? point.signups;
    totals.capableActivated += point.capableActivated ?? point.activated;
  }

  return {
    ...totals,
    rate: percent(totals.activated, totals.signups),
    capableRate: percent(totals.capableActivated, totals.capableSignups),
    telemetryCoverage: percent(totals.capableSignups, totals.signups),
  };
}
