import type { ActivationSeries } from "@/lib/growth-metrics";

/**
 * One-release compat for live Infinity panels that still read viral-metrics
 * `summary.activationRate` / `activation[]` while the checked-in omi-tv JSON
 * is not yet applied. PostHog `Memory Created` coverage stays a separate field.
 *
 * LIFECYCLE: one-time
 * DELETE-AFTER: https://github.com/BasedHardware/omi/issues/11701
 */

export type ViralActivationPoint = {
  date: string;
  week?: string;
  signups: number;
  activated: number;
  rate: number;
  capableSignups?: number;
  capableActivated?: number;
};

export type ViralMetricsSummary = {
  activationRate: number | null;
  activationTelemetryCoverage: number | null;
  activationSignups?: number;
  activationPooledRate?: number | null;
  [key: string]: unknown;
};

export type ViralMetricsPayload = {
  activation: ViralActivationPoint[];
  /** Preserved daily telemetry so `/dashboard/classic` can still roll weeks. */
  activationDaily?: ViralActivationPoint[];
  /** `week` when `activation[]` is the Firestore weekly overlay. */
  activationBucket?: "day" | "week";
  summary: ViralMetricsSummary;
  [key: string]: unknown;
};

export type FirestoreActivationCompat = ActivationSeries & {
  erroredUsers?: number;
  partial?: boolean;
};

export function isPartialFirestoreActivation(
  firestore: FirestoreActivationCompat,
): boolean {
  return (firestore.erroredUsers ?? 0) > 0 || firestore.partial === true;
}

/** Grafana omi-tv selectors: top-level `rate`, `weeks[]` with week/date. */
export type GrafanaActivationPayload = ActivationSeries & {
  weeks: Array<ActivationSeries["weeks"][number] & { date: string }>;
  /**
   * Cohort members whose per-user read failed and were dropped from the
   * sample. Non-zero means the rate is computed over a shrunken cohort, so it
   * must travel with the rate rather than being typed away here.
   */
  erroredUsers?: number;
};

export function toGrafanaActivationPayload(
  series: ActivationSeries & { erroredUsers?: number },
): GrafanaActivationPayload {
  return {
    ...series,
    weeks: series.weeks.map((week) => ({ ...week, date: week.week })),
    erroredUsers: series.erroredUsers ?? 0,
  };
}

export function applyFirestoreActivationCompat(
  viral: ViralMetricsPayload,
  firestore: FirestoreActivationCompat | null,
): ViralMetricsPayload {
  if (!firestore) return viral;
  if (isPartialFirestoreActivation(firestore)) return viral;

  return {
    ...viral,
    activationDaily: viral.activationDaily ?? viral.activation,
    activationBucket: "week",
    activation: firestore.weeks.map((week) => ({
      date: week.week,
      week: week.week,
      signups: week.signups,
      activated: week.activated,
      rate: week.rate,
    })),
    summary: {
      ...viral.summary,
      activationRate: firestore.rate,
      activationSignups: firestore.signups,
    },
  };
}
