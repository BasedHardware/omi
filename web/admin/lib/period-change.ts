export interface PeriodChange {
  percentage: number;
  label: string;
}

type MetricValue = number | null | undefined;

export function calculatePeriodChange(
  current: MetricValue,
  previous: MetricValue,
  label = "vs previous period",
): PeriodChange | null {
  if (
    current == null ||
    previous == null ||
    !Number.isFinite(current) ||
    !Number.isFinite(previous)
  ) {
    return null;
  }

  if (previous === 0) {
    return current === 0 ? { percentage: 0, label } : null;
  }

  return {
    percentage: ((current - previous) / Math.abs(previous)) * 100,
    label,
  };
}

export function latestPeriodChange<T>(
  points: readonly T[],
  value: (point: T) => MetricValue,
  label = "vs previous period",
): PeriodChange | null {
  if (points.length < 2) return null;
  return calculatePeriodChange(
    value(points[points.length - 1]),
    value(points[points.length - 2]),
    label,
  );
}

export function formatPeriodChange(percentage: number): string {
  const normalized = Math.abs(percentage) < 0.05 ? 0 : percentage;
  return (
    new Intl.NumberFormat("en-US", {
      signDisplay: "exceptZero",
      maximumFractionDigits: Math.abs(normalized) >= 10 ? 0 : 1,
    }).format(normalized) + "%"
  );
}
