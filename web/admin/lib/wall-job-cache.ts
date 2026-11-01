import type { Metric, MetricId } from "./wall-metrics";

export const WALL_SOURCE_TTL = 15 * 60_000;
export const WALL_RETRY_COOLDOWN = 30_000;

/** Successful jobs retain their own TTL while failed jobs retry on the wall's
 * short cooldown. Snapshots are copied: presentation/cohort annotations must not
 * mutate a cached source receipt or accumulate reason text on each retry.
 */
export class WallJobCache {
  private jobs = new Map<
    string,
    { day: string; expires: number; retryable: boolean; metrics: Metric[] }
  >();

  restore(ids: MetricId[], metrics: Record<MetricId, Metric>, day: string) {
    const entry = this.jobs.get(ids.join(","));
    if (!entry || entry.day !== day || Date.now() >= entry.expires)
      return false;
    for (const m of entry.metrics) metrics[m.id] = structuredClone(m);
    return entry.retryable ? "retryable" : "success";
  }

  store(
    ids: MetricId[],
    metrics: Record<MetricId, Metric>,
    day: string,
    retryable = false
  ) {
    this.jobs.set(ids.join(","), {
      day,
      expires: Date.now() + (retryable ? WALL_RETRY_COOLDOWN : WALL_SOURCE_TTL),
      retryable,
      metrics: ids.map((id) => structuredClone(metrics[id])),
    });
  }

  nextRefreshAt() {
    return Math.min(
      ...Array.from(this.jobs.values()).map((entry) => entry.expires)
    );
  }
}
