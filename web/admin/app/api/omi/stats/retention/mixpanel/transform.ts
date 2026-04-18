interface RawCohort {
  counts: number[];
  first?: number;
}

interface CohortResult {
  date: string;
  users: number;
  data: { day: number; retention: number }[];
}

export interface RetentionResult {
  data: { day: number; retention: number }[];
  cohorts: CohortResult[];
  totalCohorts: number;
  totalUsers: number;
}

/**
 * Transform raw Mixpanel retention data into retention percentages.
 * Uses cohort.first as denominator (true cohort size) so retention never exceeds 100%.
 */
export function transformRetention(raw: Record<string, RawCohort>): RetentionResult {
  const cohortDates = Object.keys(raw)
    .filter((k) => typeof raw[k] === 'object' && raw[k] !== null && 'counts' in raw[k])
    .sort();

  if (cohortDates.length === 0) {
    return { data: [], cohorts: [], totalCohorts: 0, totalUsers: 0 };
  }

  let maxDays = 0;
  for (const date of cohortDates) {
    const counts = raw[date]?.counts;
    if (Array.isArray(counts) && counts.length > maxDays) {
      maxDays = counts.length;
    }
  }

  const data: { day: number; retention: number }[] = [];
  let totalUsers = 0;
  const cohorts: CohortResult[] = [];

  for (const date of cohortDates) {
    const cohort = raw[date];
    if (!cohort || !Array.isArray(cohort.counts)) continue;

    // Use cohort.first as denominator — the true cohort size.
    // With born_where, first = users whose birth event matched the platform filter.
    // counts[N] can never exceed first, so retention is always ≤ 100%.
    const denominator = cohort.first ?? cohort.counts[0] ?? 0;
    if (denominator === 0) continue;

    totalUsers += denominator;
    const label = date.split('T')[0]; // "YYYY-MM-DD"
    const curve: { day: number; retention: number }[] = [];

    for (let dayIdx = 0; dayIdx < cohort.counts.length; dayIdx++) {
      curve.push({
        day: dayIdx,
        retention: Math.round((cohort.counts[dayIdx] / denominator) * 100 * 100) / 100,
      });
    }

    cohorts.push({ date: label, users: denominator, data: curve });
  }

  for (let dayIdx = 0; dayIdx < maxDays; dayIdx++) {
    let sumPct = 0;
    let cohortCount = 0;

    for (const date of cohortDates) {
      const cohort = raw[date];
      if (!cohort || !Array.isArray(cohort.counts)) continue;

      const denominator = cohort.first ?? cohort.counts[0] ?? 0;
      if (denominator === 0) continue;
      if (dayIdx >= cohort.counts.length) continue;

      sumPct += (cohort.counts[dayIdx] / denominator) * 100;
      cohortCount++;
    }

    if (cohortCount > 0) {
      data.push({
        day: dayIdx,
        retention: Math.round((sumPct / cohortCount) * 100) / 100,
      });
    }
  }

  return { data, cohorts, totalCohorts: cohortDates.length, totalUsers };
}
