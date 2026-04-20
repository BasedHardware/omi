import { useEffect } from "react";
import { CheckCircle2, TrendingUp } from "lucide-react";
import { useScoreStore } from "@/stores/scoreStore";

/** 0-100 → hex color ramp, mirrors Swift `ScoreWidget.scoreColor`. */
function colorForScore(score: number, hasTasks: boolean): string {
  if (!hasTasks) return "#6B7280"; // muted grey
  if (score >= 80) return "#22C55E"; // green
  if (score >= 60) return "#CCCC00"; // lime/yellow
  if (score >= 40) return "#F97316"; // orange
  return "#EF4444"; // red
}

/** SVG half-ring gauge — no external chart lib. */
function Gauge({ value, color }: { value: number; color: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  // Arc path from (10,70) to (170,70), radius 80.
  const radius = 70;
  const cx = 90;
  const cy = 80;
  const startX = cx - radius;
  const endX = cx + radius;
  const circumference = Math.PI * radius;
  const dashOffset = circumference * (1 - clamped / 100);

  return (
    <svg
      viewBox="0 0 180 100"
      className="dashboard-score-gauge"
      role="img"
      aria-label={`Score ${Math.round(clamped)} percent`}
    >
      <path
        d={`M ${startX} ${cy} A ${radius} ${radius} 0 0 1 ${endX} ${cy}`}
        stroke="var(--app-border)"
        strokeWidth={10}
        strokeLinecap="round"
        fill="none"
      />
      <path
        d={`M ${startX} ${cy} A ${radius} ${radius} 0 0 1 ${endX} ${cy}`}
        stroke={color}
        strokeWidth={10}
        strokeLinecap="round"
        fill="none"
        style={{
          strokeDasharray: circumference,
          strokeDashoffset: dashOffset,
          transition: "stroke-dashoffset 400ms ease-out, stroke 300ms ease-out",
        }}
      />
    </svg>
  );
}

/**
 * Weekly productivity score gauge — pulls from `/v1/scores`.
 *
 * Matches Swift `ScoreWidget` which reads `scoreResponse?.weekly` (last 7 days
 * of task completion).
 */
export function DailyScoreWidget() {
  const { scores, loadScores } = useScoreStore();

  useEffect(() => {
    void loadScores();
    const id = setInterval(() => void loadScores(true), 120_000);
    return () => clearInterval(id);
  }, [loadScores]);

  const weekly = scores?.weekly ?? {
    score: 0,
    completed_tasks: 0,
    total_tasks: 0,
  };
  const hasTasks = weekly.total_tasks > 0;
  const score = Math.round(weekly.score);
  const color = colorForScore(score, hasTasks);

  return (
    <section className="dashboard-card dashboard-score-card">
      <div className="dashboard-card-head">
        <div className="dashboard-card-head-icon">
          <TrendingUp size={14} />
        </div>
        <h2 className="dashboard-card-title">Weekly Score</h2>
      </div>

      <div className="dashboard-score-gauge-wrap">
        <Gauge value={hasTasks ? weekly.score : 0} color={color} />
        <div className="dashboard-score-value" style={{ color }}>
          {hasTasks ? `${score}%` : "—"}
        </div>
      </div>

      <div className="dashboard-score-meta">
        {hasTasks ? (
          <>
            <CheckCircle2 size={13} style={{ color }} />
            <span className="tabular-nums">
              {weekly.completed_tasks} of {weekly.total_tasks} tasks completed
            </span>
          </>
        ) : (
          <span>No tasks this week</span>
        )}
      </div>
      <p className="dashboard-score-sub">Last 7 days</p>
    </section>
  );
}
