import { useEffect } from "react";
import { TrendingUp } from "lucide-react";
import { useScoreStore } from "@/stores/scoreStore";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

function colorForScore(score: number, hasTasks: boolean): string {
  if (!hasTasks) return "var(--muted-foreground)";
  if (score >= 80) return "#22C55E";
  if (score >= 60) return "#CCCC00";
  if (score >= 40) return "#F97316";
  return "#EF4444";
}

function Gauge({ value, color }: { value: number; color: string }) {
  const clamped = Math.max(0, Math.min(100, value));
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
      className="h-full w-full"
      role="img"
      aria-label={`Score ${Math.round(clamped)} percent`}
    >
      <path
        d={`M ${startX} ${cy} A ${radius} ${radius} 0 0 1 ${endX} ${cy}`}
        stroke="var(--border)"
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
    <Card className="h-full gap-3 border-border/50 bg-card/40 py-5 shadow-none">
      <CardHeader className="px-5">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <TrendingUp size={14} />
          Weekly Score
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-2 px-5">
        <div className="relative flex h-[100px] w-full max-w-[200px] items-end justify-center">
          <Gauge value={hasTasks ? weekly.score : 0} color={color} />
          <div
            className="absolute bottom-1 left-1/2 -translate-x-1/2 text-3xl font-semibold tabular-nums tracking-tight"
            style={{ color }}
          >
            {hasTasks ? `${score}%` : "—"}
          </div>
        </div>
        <div className="text-center text-xs text-muted-foreground">
          {hasTasks ? (
            <span className="tabular-nums">
              {weekly.completed_tasks} of {weekly.total_tasks} tasks · last 7 days
            </span>
          ) : (
            <span>No tasks this week</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
