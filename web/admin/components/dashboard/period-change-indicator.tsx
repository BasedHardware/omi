import { cn } from "@/lib/utils";
import { formatPeriodChange, type PeriodChange } from "@/lib/period-change";

export function PeriodChangeIndicator({
  change,
  className,
}: {
  change: PeriodChange | null | undefined;
  className?: string;
}) {
  if (!change) return null;

  const formatted = formatPeriodChange(change.percentage);
  const description = `${formatted} ${change.label}`;

  return (
    <span
      aria-label={description}
      title={description}
      className={cn(
        "shrink-0 text-xs font-semibold tabular-nums",
        change.percentage > 0 && "text-green-600 dark:text-green-400",
        change.percentage < 0 && "text-red-600 dark:text-red-400",
        change.percentage === 0 && "text-muted-foreground",
        className,
      )}
    >
      {formatted}
    </span>
  );
}
