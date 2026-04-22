import { Eye, Focus, Activity, AlertCircle, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  useFocusStats,
  useFocusStore,
  type TopDistraction,
} from "@/stores/focusStore";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";

const FOCUS_COLOR = "#22C55E";
const DISTRACTED_COLOR = "#F97316";
const NEUTRAL_COLOR = "#3B82F6";

function formatMinutes(mins: number): string {
  if (mins <= 0) return "0m";
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s`;
  const mins = Math.round(seconds / 60);
  return formatMinutes(mins);
}

function rateColor(rate: number, hasData: boolean): string {
  if (!hasData) return "var(--muted-foreground)";
  if (rate >= 75) return FOCUS_COLOR;
  if (rate >= 50) return NEUTRAL_COLOR;
  if (rate >= 25) return "#EAB308";
  return DISTRACTED_COLOR;
}

function StatBody({
  value,
  label,
  color,
  labelSuffix,
}: {
  value: string | number;
  label: string;
  color?: string;
  labelSuffix?: ReactNode;
}) {
  return (
    <>
      <span
        className="text-lg font-semibold tabular-nums tracking-tight text-foreground"
        style={color ? { color } : undefined}
      >
        {value}
      </span>
      <span className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/80">
        {label}
        {labelSuffix}
      </span>
    </>
  );
}

function Stat(props: {
  value: string | number;
  label: string;
  color?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <StatBody {...props} />
    </div>
  );
}

function DistractionsHoverCard({
  children,
  align,
  distractions,
  onViewAll,
}: {
  children: ReactNode;
  align: "start" | "center" | "end";
  distractions: TopDistraction[];
  onViewAll: () => void;
}) {
  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent align={align} className="w-72 p-3">
        <TopDistractionsContent
          distractions={distractions}
          onViewAll={onViewAll}
        />
      </HoverCardContent>
    </HoverCard>
  );
}

function TopDistractionsContent({
  distractions,
  onViewAll,
}: {
  distractions: TopDistraction[];
  onViewAll: () => void;
}) {
  return (
    <>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-foreground">
          Top distractions today
        </span>
        <span className="text-[10px] tabular-nums text-muted-foreground">
          {distractions.length} {distractions.length === 1 ? "app" : "apps"}
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {distractions.map((d) => (
          <li
            key={d.app}
            className="flex items-center justify-between gap-2 text-xs"
          >
            <span
              className="truncate font-medium text-foreground"
              title={d.app}
            >
              {d.app}
            </span>
            <span className="flex shrink-0 items-center gap-2 tabular-nums text-muted-foreground">
              <span style={{ color: DISTRACTED_COLOR }}>
                {formatDuration(d.totalSeconds)}
              </span>
              <span className="text-muted-foreground/60">{d.count}×</span>
            </span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={onViewAll}
        className="mt-3 flex w-full items-center justify-center gap-1 rounded-md border border-border/60 bg-accent/30 px-2 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-accent"
      >
        View full focus history
        <ChevronRight size={11} />
      </button>
    </>
  );
}

export function FocusSummaryWidget() {
  const navigate = useNavigate();
  const stats = useFocusStats();
  const currentStatus = useFocusStore((s) => s.currentStatus);
  const focusEnabled = useFocusStore((s) => s.focusEnabled);
  const hasData = stats.sessionCount > 0;

  const rate = stats.focusRate;
  const rateCol = rateColor(rate, hasData);
  const focusedPct = Math.max(0, Math.min(100, rate));
  const distractedPct = 100 - focusedPct;

  const topDistraction = stats.topDistractions[0];
  const statusLabel = !focusEnabled
    ? "Paused"
    : currentStatus === "focused"
      ? "Focused"
      : currentStatus === "distracted"
        ? "Distracted"
        : "Watching";
  const statusColor = !focusEnabled
    ? "var(--muted-foreground)"
    : currentStatus === "focused"
      ? FOCUS_COLOR
      : currentStatus === "distracted"
        ? DISTRACTED_COLOR
        : NEUTRAL_COLOR;

  const focusBar = (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-border/50 transition-all duration-200 group-hover:h-2.5">
      <div
        className="h-full transition-all duration-500"
        style={{ width: `${focusedPct}%`, backgroundColor: FOCUS_COLOR }}
      />
      <div
        className="h-full transition-all duration-500"
        style={{
          width: `${distractedPct}%`,
          backgroundColor: DISTRACTED_COLOR,
          opacity: 0.85,
        }}
      />
    </div>
  );

  return (
    <Card className="h-full gap-3 border-border/50 bg-card/40 py-5 shadow-none">
      <CardHeader className="px-5">
        <CardTitle className="flex items-center justify-between text-sm font-medium text-muted-foreground">
          <span className="flex items-center gap-2">
            <Focus size={14} />
            Focus Today
          </span>
          <span
            className="flex items-center gap-1.5 text-[11px] font-medium"
            style={{ color: statusColor }}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: statusColor }}
            />
            {statusLabel}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="px-5">
        {hasData ? (
          <div className="flex flex-col gap-4">
            <div className="flex items-end justify-between gap-4">
              <div className="flex flex-col gap-0.5">
                <span
                  className="text-3xl font-semibold tabular-nums tracking-tight"
                  style={{ color: rateCol }}
                >
                  {rate}%
                </span>
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/80">
                  Focus Rate
                </span>
              </div>
              <div className="flex flex-col items-end gap-0.5 text-right">
                <span className="text-xs tabular-nums text-muted-foreground">
                  {formatMinutes(stats.focusMinutes + stats.distractedMinutes)} tracked
                </span>
                {topDistraction && (
                  <DistractionsHoverCard
                    align="end"
                    distractions={stats.topDistractions}
                    onViewAll={() => navigate("/focus")}
                  >
                    <button
                      type="button"
                      onClick={() => navigate("/focus")}
                      className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground/80 transition-colors hover:bg-accent/50 hover:text-foreground focus-visible:bg-accent/50 focus-visible:outline-none"
                    >
                      <AlertCircle size={10} style={{ color: DISTRACTED_COLOR }} />
                      <span className="max-w-[140px] truncate">
                        Top distraction: {topDistraction.app}
                      </span>
                      <ChevronRight size={10} className="opacity-60" />
                    </button>
                  </DistractionsHoverCard>
                )}
              </div>
            </div>

            {topDistraction ? (
              <DistractionsHoverCard
                align="center"
                distractions={stats.topDistractions}
                onViewAll={() => navigate("/focus")}
              >
                <button
                  type="button"
                  aria-label={`Focus breakdown: ${focusedPct}% focused, ${distractedPct}% distracted`}
                  className="group -my-2 block w-full cursor-pointer bg-transparent py-2 focus-visible:outline-none"
                >
                  {focusBar}
                </button>
              </DistractionsHoverCard>
            ) : (
              focusBar
            )}

            <div className="grid grid-cols-3 gap-4">
              <Stat
                value={formatMinutes(stats.focusMinutes)}
                label="Focused"
                color={FOCUS_COLOR}
              />
              {topDistraction ? (
                <DistractionsHoverCard
                  align="center"
                  distractions={stats.topDistractions}
                  onViewAll={() => navigate("/focus")}
                >
                  <button
                    type="button"
                    aria-label={`Distracted ${formatMinutes(stats.distractedMinutes)} — top distractions`}
                    className="-mx-1.5 -my-1 flex flex-col items-start gap-0.5 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none"
                  >
                    <StatBody
                      value={formatMinutes(stats.distractedMinutes)}
                      label="Distracted"
                      color={DISTRACTED_COLOR}
                      labelSuffix={
                        <AlertCircle
                          size={9}
                          className="opacity-60"
                          style={{ color: DISTRACTED_COLOR }}
                        />
                      }
                    />
                  </button>
                </DistractionsHoverCard>
              ) : (
                <Stat
                  value={formatMinutes(stats.distractedMinutes)}
                  label="Distracted"
                  color={DISTRACTED_COLOR}
                />
              )}
              <Stat value={stats.sessionCount} label="Sessions" />
            </div>
          </div>
        ) : (
          <div className="flex h-24 flex-col items-center justify-center gap-1.5 text-center text-muted-foreground">
            {focusEnabled ? (
              <Activity size={20} style={{ color: NEUTRAL_COLOR, opacity: 0.7 }} />
            ) : (
              <Eye size={20} className="opacity-50" />
            )}
            <span className="text-sm font-medium text-foreground">
              {focusEnabled ? "Watching your screen" : "Turn on Rewind"}
            </span>
            <span className="text-xs">
              {focusEnabled
                ? "Focus insights appear as sessions accumulate."
                : "Focus insights appear once monitoring collects data."}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
