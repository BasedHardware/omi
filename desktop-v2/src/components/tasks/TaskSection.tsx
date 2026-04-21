import { useState } from "react";
import {
  AlertCircle,
  Calendar,
  CalendarClock,
  ChevronRight,
  Inbox,
  Sun,
  Sunrise,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { DueBucket } from "./taskDates";

const BUCKET_ICONS: Record<DueBucket, LucideIcon> = {
  overdue: AlertCircle,
  today: Sun,
  tomorrow: Sunrise,
  thisWeek: CalendarClock,
  later: Calendar,
  noDate: Inbox,
};

const BUCKET_TONE: Record<DueBucket, string> = {
  overdue: "task-section-danger",
  today: "task-section-warn",
  tomorrow: "",
  thisWeek: "",
  later: "",
  noDate: "",
};

interface Props {
  bucket: DueBucket;
  label: string;
  hint: string;
  count: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export function TaskSection({
  bucket,
  label,
  hint,
  count,
  defaultOpen = true,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const Icon = BUCKET_ICONS[bucket];
  const tone = BUCKET_TONE[bucket];

  return (
    <section className="task-section">
      <button
        type="button"
        className={`task-section-head ${tone}`}
        onClick={() => setOpen((v) => !v)}
      >
        <ChevronRight
          size={14}
          className={`task-section-chevron ${open ? "task-section-chevron-open" : ""}`}
        />
        <Icon size={14} className="task-section-icon" />
        <span className="task-section-label">{label}</span>
        <span className="task-section-count">{count}</span>
        {hint && <span className="task-section-hint">{hint}</span>}
      </button>
      {open && <div className="task-section-body">{children}</div>}
    </section>
  );
}
