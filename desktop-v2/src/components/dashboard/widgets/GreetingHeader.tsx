import { Fragment, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTaskStore } from "@/stores/taskStore";
import { bucketFor } from "@/components/tasks/taskDates";
import { cn } from "@/lib/utils";

function weekOfYear(date: Date): number {
  const start = new Date(date.getFullYear(), 0, 1);
  const diff = date.getTime() - start.getTime();
  const day = Math.floor(diff / 86_400_000);
  return Math.ceil((day + start.getDay() + 1) / 7);
}

function shortDate(date: Date): string {
  return date.toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

type StatusPart = {
  key: string;
  text: string;
  to?: string;
  tone?: "default" | "danger" | "warn";
};

export function GreetingHeader() {
  const tasks = useTaskStore((s) => s.tasks);
  const navigate = useNavigate();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const parts = useMemo<StatusPart[]>(() => {
    const open = tasks.filter((t) => !t.completed);
    const overdue = open.filter((t) => bucketFor(t, now) === "overdue").length;
    const today = open.filter((t) => bucketFor(t, now) === "today").length;
    const list: StatusPart[] = [];
    if (overdue > 0) {
      list.push({
        key: "overdue",
        text: `${overdue} overdue`,
        to: "/tasks?filter=overdue",
        tone: "danger",
      });
    }
    if (today > 0) {
      list.push({
        key: "today",
        text: `${today} due today`,
        to: "/tasks?filter=today",
        tone: "warn",
      });
    }
    if (list.length === 0 && open.length > 0) {
      list.push({
        key: "queue",
        text: `${open.length} in your queue`,
        to: "/tasks",
      });
    }
    if (list.length === 0) {
      list.push({
        key: "quiet",
        text: "Nothing due — a quiet day.",
      });
    }
    return list;
  }, [tasks, now]);

  return (
    <header className="flex items-baseline justify-between gap-4">
      <div className="flex flex-col gap-0.5">
        <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground/70 tabular-nums">
          {shortDate(now)} · Week {weekOfYear(now)}
        </p>
        <h1 className="text-sm font-medium text-foreground/90">
          {parts.map((p, i) => (
            <Fragment key={p.key}>
              {i > 0 && <span className="text-muted-foreground/50"> · </span>}
              {p.to ? (
                <button
                  type="button"
                  onClick={() => navigate(p.to!)}
                  className={cn(
                    "rounded-sm underline-offset-4 transition-colors hover:underline",
                    p.tone === "danger" && "text-destructive hover:text-destructive",
                    p.tone === "warn" && "text-amber-500 hover:text-amber-400",
                    p.tone === "default" && "hover:text-foreground",
                  )}
                >
                  {p.text}
                </button>
              ) : (
                <span>{p.text}</span>
              )}
            </Fragment>
          ))}
        </h1>
      </div>
    </header>
  );
}
