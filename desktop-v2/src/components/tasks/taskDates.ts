import type { Task } from "../../stores/taskStore";

export type DueBucket =
  | "overdue"
  | "today"
  | "tomorrow"
  | "thisWeek"
  | "later"
  | "noDate";

const MS_PER_DAY = 86_400_000;

function startOfDay(d: Date): Date {
  const copy = new Date(d);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

export function bucketFor(task: Task, now: Date = new Date()): DueBucket {
  if (!task.due_at) return "noDate";
  const due = new Date(task.due_at);
  if (Number.isNaN(due.getTime())) return "noDate";

  const today = startOfDay(now);
  const tomorrow = new Date(today.getTime() + MS_PER_DAY);
  const dayAfter = new Date(today.getTime() + 2 * MS_PER_DAY);
  const endOfWeek = new Date(today.getTime() + 7 * MS_PER_DAY);

  if (due < today) return "overdue";
  if (due < tomorrow) return "today";
  if (due < dayAfter) return "tomorrow";
  if (due < endOfWeek) return "thisWeek";
  return "later";
}

export function dueLabel(iso: string, now: Date = new Date()): string {
  const due = new Date(iso);
  if (Number.isNaN(due.getTime())) return "";

  const today = startOfDay(now);
  const tomorrow = new Date(today.getTime() + MS_PER_DAY);
  const dayAfter = new Date(today.getTime() + 2 * MS_PER_DAY);
  const endOfWeek = new Date(today.getTime() + 7 * MS_PER_DAY);

  if (due < today) {
    const days = Math.floor((today.getTime() - due.getTime()) / MS_PER_DAY);
    if (days === 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return `${days}d overdue`;
    return due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  if (due < tomorrow) return "Today";
  if (due < dayAfter) return "Tomorrow";
  if (due < endOfWeek) {
    return due.toLocaleDateString(undefined, { weekday: "long" });
  }
  return due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function isNew(task: Task, now: Date = new Date()): boolean {
  if (!task.created_at) return false;
  const created = new Date(task.created_at);
  if (Number.isNaN(created.getTime())) return false;
  return now.getTime() - created.getTime() < 60_000;
}

export const BUCKET_META: Record<
  DueBucket,
  { label: string; hint: string; order: number }
> = {
  overdue: { label: "Overdue", hint: "Needs attention", order: 0 },
  today: { label: "Today", hint: "Due today", order: 1 },
  tomorrow: { label: "Tomorrow", hint: "", order: 2 },
  thisWeek: { label: "This week", hint: "", order: 3 },
  later: { label: "Later", hint: "", order: 4 },
  noDate: { label: "No date", hint: "Unscheduled", order: 5 },
};
