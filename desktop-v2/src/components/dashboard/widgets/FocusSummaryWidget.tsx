import { Eye, Focus } from "lucide-react";
import { useFocusStats } from "@/stores/focusStore";

function formatMinutes(mins: number): string {
  if (mins <= 0) return "0m";
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/**
 * Focus summary — sessions today + total focused time. Pulls from the local
 * focusStore (persisted to `focus-history.json`). Renders a subdued skeleton
 * when there's no data yet so the dashboard doesn't feel broken on day one.
 */
export function FocusSummaryWidget() {
  const stats = useFocusStats();
  const hasData = stats.sessionCount > 0;

  return (
    <section className="dashboard-card dashboard-focus-card">
      <div className="dashboard-card-head">
        <div className="dashboard-card-head-icon">
          <Focus size={14} />
        </div>
        <h2 className="dashboard-card-title">Focus Today</h2>
      </div>

      {hasData ? (
        <div className="dashboard-focus-stats">
          <div className="dashboard-focus-stat">
            <span className="dashboard-focus-stat-value tabular-nums">
              {formatMinutes(stats.focusMinutes)}
            </span>
            <span className="dashboard-focus-stat-label">Focused</span>
          </div>
          <div className="dashboard-focus-stat">
            <span
              className="dashboard-focus-stat-value tabular-nums"
              style={{ color: "#F97316" }}
            >
              {formatMinutes(stats.distractedMinutes)}
            </span>
            <span className="dashboard-focus-stat-label">Distracted</span>
          </div>
          <div className="dashboard-focus-stat">
            <span className="dashboard-focus-stat-value tabular-nums">
              {stats.focusRate}%
            </span>
            <span className="dashboard-focus-stat-label">Focus Rate</span>
          </div>
          <div className="dashboard-focus-stat">
            <span className="dashboard-focus-stat-value tabular-nums">
              {stats.sessionCount}
            </span>
            <span className="dashboard-focus-stat-label">Sessions</span>
          </div>
        </div>
      ) : (
        <div className="dashboard-focus-empty">
          <Eye size={18} className="dashboard-focus-empty-icon" />
          <span className="dashboard-focus-empty-title">Turn on Rewind</span>
          <span className="dashboard-focus-empty-sub">
            Focus insights appear once monitoring collects data.
          </span>
        </div>
      )}
    </section>
  );
}
