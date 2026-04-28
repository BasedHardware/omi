import { useMemo } from "react";
import type { Task } from "../../stores/taskStore";
import { bucketFor } from "./taskDates";
import {
  PageHeader,
  PageHeaderFilter,
  PageHeaderFilters,
} from "../ui/page-header";

export type FilterKey = "all" | "overdue" | "today" | "nodate" | "done";

/** Source filter is orthogonal to the date filter — pick a tracker to scope
 *  to ("only Jira") and stack with "Today" / "Overdue" etc. */
export type SourceKey = "all" | "native" | string; // also accepts task.source values like "jira"

interface Props {
  tasks: Task[];
  stagedCount: number;
  filter: FilterKey;
  onFilter: (key: FilterKey) => void;
  sourceFilter: SourceKey;
  onSourceFilter: (key: SourceKey) => void;
}

const SOURCE_LABEL: Record<string, string> = {
  native: "Nooto",
  jira: "Jira",
  linear: "Linear",
};

function isToday(d: Date, now: Date): boolean {
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function TasksHeader({
  tasks,
  stagedCount,
  filter,
  onFilter,
  sourceFilter,
  onSourceFilter,
}: Props) {
  const stats = useMemo(() => {
    const now = new Date();
    let open = 0;
    let overdue = 0;
    let today = 0;
    let noDate = 0;
    let doneToday = 0;
    // Per-source open-task counts so the source filter row matches the
    // current open scope (date-completed tickets shouldn't inflate "Jira · 12").
    const bySource: Record<string, number> = {};
    for (const t of tasks) {
      if (!t.completed) {
        open += 1;
        const b = bucketFor(t, now);
        if (b === "overdue") overdue += 1;
        if (b === "today") today += 1;
        if (b === "noDate") noDate += 1;
        const src = t.source && t.source !== "native" ? t.source : "native";
        bySource[src] = (bySource[src] ?? 0) + 1;
      } else if (t.completed_at) {
        const at = new Date(t.completed_at);
        if (!Number.isNaN(at.getTime()) && isToday(at, now)) doneToday += 1;
      }
    }
    return { open, overdue, today, noDate, doneToday, bySource };
  }, [tasks]);

  if (tasks.length === 0 && stagedCount === 0) return null;

  const filters: { key: FilterKey; label: string; count: number }[] = [
    { key: "all", label: "All", count: stats.open },
    { key: "overdue", label: "Overdue", count: stats.overdue },
    { key: "today", label: "Today", count: stats.today },
    { key: "nodate", label: "No date", count: stats.noDate },
    { key: "done", label: "Completed", count: tasks.length - stats.open },
  ];

  // Build source filter chips: always show "All", then a chip per source that
  // currently has open tasks (so empty trackers don't clutter the row). Order:
  // Nooto first, then alphabetical.
  const sourceKeys = Object.keys(stats.bySource);
  sourceKeys.sort((a, b) => {
    if (a === "native") return -1;
    if (b === "native") return 1;
    return a.localeCompare(b);
  });
  const sourceChips: { key: SourceKey; label: string; count: number }[] = [
    { key: "all", label: "All sources", count: stats.open },
    ...sourceKeys.map((k) => ({
      key: k as SourceKey,
      label: SOURCE_LABEL[k] ?? k,
      count: stats.bySource[k] ?? 0,
    })),
  ];

  const parts: string[] = [`${stats.open} open`];
  if (stats.overdue > 0) parts.push(`${stats.overdue} overdue`);
  if (stats.doneToday > 0) parts.push(`${stats.doneToday} done today`);
  if (stagedCount > 0) parts.push(`${stagedCount} suggested`);

  // The source filter row only renders when at least one integration source
  // has tasks — keeps single-source users (just Nooto, no plugins) clutter-free.
  const hasIntegrationTasks = sourceKeys.some((k) => k !== "native");

  return (
    <PageHeader title="Tasks" subtitle={parts.join(" · ")}>
      <PageHeaderFilters>
        {filters.map((f) => {
          if (f.count === 0 && f.key !== "all") return null;
          return (
            <PageHeaderFilter
              key={f.key}
              active={filter === f.key}
              onClick={() => onFilter(f.key)}
              count={f.count}
            >
              {f.label}
            </PageHeaderFilter>
          );
        })}
      </PageHeaderFilters>
      {hasIntegrationTasks && (
        <PageHeaderFilters>
          {sourceChips.map((s) => (
            <PageHeaderFilter
              key={s.key}
              active={sourceFilter === s.key}
              onClick={() => onSourceFilter(s.key)}
              count={s.count}
            >
              {s.label}
            </PageHeaderFilter>
          ))}
        </PageHeaderFilters>
      )}
    </PageHeader>
  );
}
