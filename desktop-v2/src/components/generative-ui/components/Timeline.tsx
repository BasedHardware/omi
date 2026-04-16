import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../ui/card";
import { Badge } from "../../ui/badge";
import type { TimelineData, TimelineLabel } from "../types";

const LABEL_COLOR: Record<TimelineLabel, string> = {
  context: "#3B82F6",
  conflict: "#EF4444",
  claim: "#F59E0B",
  decision: "#22C55E",
  reaction: "#8B5CF6",
  humanImpact: "#EC4899",
  nextSteps: "#06B6D4",
  other: "#6B7280",
};

export function Timeline({
  data,
  embedded = false,
}: {
  data: TimelineData;
  embedded?: boolean;
}) {
  const list = (
    <ol className="relative space-y-5 border-l pl-6">
      {data.events.map((ev, i) => {
        const color = LABEL_COLOR[ev.labelType];
        return (
          <li key={i} className="relative">
            <span
              aria-hidden
              className="absolute -left-[27px] top-1.5 size-2.5 rounded-full ring-4 ring-background"
              style={{ backgroundColor: color }}
            />
            <div className="flex flex-wrap items-center gap-2">
              {ev.time && (
                <span className="font-mono text-xs text-muted-foreground tabular-nums">
                  {ev.time}
                </span>
              )}
              <Badge
                variant="outline"
                style={{ color, borderColor: `${color}55` }}
                className="font-normal"
              >
                {ev.label}
              </Badge>
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-foreground">
              {ev.description}
            </p>
          </li>
        );
      })}
    </ol>
  );

  if (embedded) return list;

  return (
    <Card className="not-prose my-3 gap-0 border-border/60 py-0">
      <CardHeader className="border-b border-border/40 px-5 py-3">
        <CardTitle className="text-sm">{data.title ?? "Timeline"}</CardTitle>
        <CardDescription className="text-xs">
          {data.events.length} {data.events.length === 1 ? "event" : "events"}
        </CardDescription>
        <CardAction />
      </CardHeader>
      <CardContent className="px-5 py-4">{list}</CardContent>
    </Card>
  );
}
