const DAY_MS = 86_400_000;

export interface DailyNewUsersPoint {
  date: string;
  users: number;
}

export interface WeeklyNewUsersPoint {
  week: string;
  users: number;
}

export interface WeeklyGrowthInput {
  week: string;
  active: number;
  newUsers: number;
  retained: number;
}

export interface WeeklyGrowthPoint extends WeeklyGrowthInput {
  resurrected: number;
  /** People active in the previous complete week who are inactive this week. */
  inactive: number;
  /** Denominator for inactiveRate: prior week's active people. */
  priorActive: number;
  inactiveRate: number | null;
  /** Negative visualization value for stacked growth charts. */
  inactiveLoss: number;
  netActiveChange: number;
}

export interface EstablishedRetentionInput {
  week: string;
  established: number;
  retained: number;
}

export interface EstablishedRetentionPoint extends EstablishedRetentionInput {
  rate: number | null;
}

export interface RollingGrowthSummary {
  active: number;
  priorActive: number;
  newUsers: number;
  retained: number;
  resurrected: number;
  inactive: number;
  inactiveRate: number | null;
  netActiveChange: number;
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

/** Return the Monday for the UTC calendar week containing `value`. */

export function mondayKey(value: string | Date): string | null {
  const date = utcDate(value);
  if (!date) return null;
  date.setUTCHours(0, 0, 0, 0);
  const daysSinceMonday = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - daysSinceMonday);
  return date.toISOString().slice(0, 10);
}

function dateDaysAgo(today: Date, days: number): Date {
  const result = new Date(today.getTime());
  result.setUTCDate(result.getUTCDate() - days);
  return result;
}

/**
 * Build growth accounting from complete UTC calendar weeks only.
 *
 * Callers should include at least one prior week in the query so the first
 * returned point has a real prior-active denominator. The extra context is
 * discarded after the previous-week comparison is computed.
 */
export function completedWeeklyGrowthAccounting(
  points: readonly WeeklyGrowthInput[],
  today = new Date(),
  days = 60
): WeeklyGrowthPoint[] {
  const currentWeek = mondayKey(today);
  const todayUtc = utcDate(today);
  if (!currentWeek || !todayUtc || !Number.isFinite(days) || days < 0)
    return [];

  const historyStart = mondayKey(dateDaysAgo(todayUtc, days));
  if (!historyStart) return [];

  const byWeek = new Map<string, WeeklyGrowthInput>();
  for (const point of points) {
    const week = mondayKey(point.week);
    if (
      !week ||
      week >= currentWeek ||
      week < historyStart ||
      !Number.isFinite(point.active) ||
      !Number.isFinite(point.newUsers) ||
      !Number.isFinite(point.retained)
    ) {
      continue;
    }
    // Query results are already grouped. Replacing duplicates rather than
    // summing prevents a duplicated partial bucket from inflating WAU.
    byWeek.set(week, { ...point, week });
  }

  const allPoints = new Map<string, WeeklyGrowthInput>();
  for (const point of points) {
    const week = mondayKey(point.week);
    if (
      !week ||
      week >= currentWeek ||
      !Number.isFinite(point.active) ||
      !Number.isFinite(point.newUsers) ||
      !Number.isFinite(point.retained)
    ) {
      continue;
    }
    allPoints.set(week, { ...point, week });
  }

  const completedWeeks: WeeklyGrowthInput[] = [];
  const currentWeekDate = new Date(`${currentWeek}T00:00:00Z`);
  for (
    const cursor = new Date(`${historyStart}T00:00:00Z`);
    cursor < currentWeekDate;
    cursor.setUTCDate(cursor.getUTCDate() + 7)
  ) {
    const week = cursor.toISOString().slice(0, 10);
    completedWeeks.push(
      byWeek.get(week) ?? {
        week,
        active: 0,
        newUsers: 0,
        retained: 0,
      }
    );
  }

  return completedWeeks.map((point) => {
    const previousWeek = new Date(`${point.week}T00:00:00Z`);
    previousWeek.setUTCDate(previousWeek.getUTCDate() - 7);
    const previousKey = previousWeek.toISOString().slice(0, 10);
    const priorActive = allPoints.get(previousKey)?.active ?? 0;
    const resurrected = Math.max(
      0,
      point.active - point.newUsers - point.retained
    );
    const inactive = Math.max(0, priorActive - point.retained);
    return {
      ...point,
      resurrected,
      inactive,
      priorActive,
      inactiveRate: percent(inactive, priorActive),
      inactiveLoss: -inactive,
      netActiveChange: point.active - priorActive,
    };
  });
}

/** Keep established-user retention on complete UTC weeks and expose its n. */
export function completedEstablishedRetention(
  points: readonly EstablishedRetentionInput[],
  today = new Date(),
  days = 60
): EstablishedRetentionPoint[] {
  const currentWeek = mondayKey(today);
  const todayUtc = utcDate(today);
  if (!currentWeek || !todayUtc || !Number.isFinite(days) || days < 0)
    return [];
  const historyStart = mondayKey(dateDaysAgo(todayUtc, days));
  if (!historyStart) return [];

  const byWeek = new Map<string, EstablishedRetentionInput>();
  for (const point of points) {
    const week = mondayKey(point.week);
    if (
      !week ||
      week >= currentWeek ||
      week < historyStart ||
      !Number.isFinite(point.established) ||
      !Number.isFinite(point.retained)
    ) {
      continue;
    }
    byWeek.set(week, { ...point, week });
  }
  return Array.from(byWeek.values())
    .sort((a, b) => a.week.localeCompare(b.week))
    .map((point) => ({
      ...point,
      rate: percent(point.retained, point.established),
    }));
}

export function rollingGrowthSummary(values: {
  active: number;
  priorActive: number;
  newUsers: number;
  retained: number;
}): RollingGrowthSummary {
  const resurrected = Math.max(
    0,
    values.active - values.newUsers - values.retained
  );
  const inactive = Math.max(0, values.priorActive - values.retained);
  return {
    ...values,
    resurrected,
    inactive,
    inactiveRate: percent(inactive, values.priorActive),
    netActiveChange: values.active - values.priorActive,
  };
}

export function completedWeeklyNewUsers(
  points: readonly DailyNewUsersPoint[],
  today = new Date()
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
    a.week.localeCompare(b.week)
  );
}

export function maturedWeeklyActivation(
  points: readonly DailyActivationPoint[],
  today = new Date(),
  maturityDays = 7
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
      weekStart.getTime() + (7 + maturityDays) * DAY_MS
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
  members: readonly ActivationCohortMember[]
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
  maturityDays = 7
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
