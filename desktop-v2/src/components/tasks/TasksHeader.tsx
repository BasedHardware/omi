import { useMemo } from "react";
import type { Task } from "../../stores/taskStore";
import { bucketFor } from "./taskDates";
import {
  PageHeader,
  PageHeaderFilter,
  PageHeaderFilters,
} from "../ui/page-header";

export type FilterKey = "all" | "overdue" | "today" | "nodate" | "done";

interface Props {
  tasks: Task[];
  stagedCount: number;
  filter: FilterKey;
  onFilter: (key: FilterKey) => void;
}

function isToday(d: Date, now: Date): boolean {
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function TasksHeader({ tasks, stagedCount, filter, onFilter }: Props) {
  const stats = useMemo(() => {
    const now = new Date();
    let open = 0;
    let overdue = 0;
    let today = 0;
    let noDate = 0;
    let doneToday = 0;
    for (const t of tasks) {
      if (!t.completed) {
        open += 1;
        const b = bucketFor(t, now);
        if (b === "overdue") overdue += 1;
        if (b === "today") today += 1;
        if (b === "noDate") noDate += 1;
      } else if (t.completed_at) {
        const at = new Date(t.completed_at);
        if (!Number.isNaN(at.getTime()) && isToday(at, now)) doneToday += 1;
      }
    }
    return { open, overdue, today, noDate, doneToday };
  }, [tasks]);

  if (tasks.length === 0 && stagedCount === 0) return null;

  const filters: { key: FilterKey; label: string; count: number }[] = [
    { key: "all", label: "All", count: stats.open },
    { key: "overdue", label: "Overdue", count: stats.overdue },
    { key: "today", label: "Today", count: stats.today },
    { key: "nodate", label: "No date", count: stats.noDate },
    { key: "done", label: "Completed", count: tasks.length - stats.open },
  ];

  const parts: string[] = [`${stats.open} open`];
  if (stats.overdue > 0) parts.push(`${stats.overdue} overdue`);
  if (stats.doneToday > 0) parts.push(`${stats.doneToday} done today`);
  if (stagedCount > 0) parts.push(`${stagedCount} suggested`);

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
    </PageHeader>
  );
}
