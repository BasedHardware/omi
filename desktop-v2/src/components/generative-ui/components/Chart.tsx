import {
  Bar,
  BarChart as RBarChart,
  Cell,
  Legend,
  Pie,
  PieChart as RPieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../ui/card";
import type { ChartData } from "../types";

const TOOLTIP_STYLE: React.CSSProperties = {
  background: "hsl(var(--popover))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "var(--radius)",
  fontSize: 12,
  padding: "6px 10px",
};

export function Chart({ data }: { data: ChartData }) {
  const total = data.segments.reduce((a, s) => a + s.value, 0);

  return (
    <Card className="not-prose my-3 gap-0 border-border/60 py-0">
      <CardHeader className="border-b border-border/40 px-5 py-3">
        <CardTitle className="text-sm">{data.title ?? "Breakdown"}</CardTitle>
        <CardDescription className="text-xs">
          {data.segments.length} {data.segments.length === 1 ? "segment" : "segments"} · total {total.toLocaleString()}
        </CardDescription>
        <CardAction />
      </CardHeader>
      <CardContent className="h-64 px-4 py-4">
        <ResponsiveContainer width="100%" height="100%">
          {data.kind === "bar" ? renderBar(data) : renderPie(data)}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function renderBar(data: ChartData) {
  return (
    <RBarChart data={data.segments} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
      <XAxis
        dataKey="label"
        stroke="currentColor"
        className="text-muted-foreground"
        fontSize={11}
        tickLine={false}
        axisLine={false}
      />
      <YAxis
        stroke="currentColor"
        className="text-muted-foreground"
        fontSize={11}
        tickLine={false}
        axisLine={false}
      />
      <Tooltip cursor={{ fill: "hsl(var(--muted) / 0.4)" }} contentStyle={TOOLTIP_STYLE} />
      <Bar dataKey="value" radius={[6, 6, 0, 0]}>
        {data.segments.map((s, i) => (
          <Cell key={i} fill={s.color} />
        ))}
      </Bar>
    </RBarChart>
  );
}

function renderPie(data: ChartData) {
  return (
    <RPieChart>
      <Tooltip contentStyle={TOOLTIP_STYLE} />
      <Legend
        verticalAlign="bottom"
        iconType="circle"
        iconSize={8}
        wrapperStyle={{ fontSize: 11, paddingTop: 4 }}
      />
      <Pie
        data={data.segments}
        dataKey="value"
        nameKey="label"
        innerRadius={data.kind === "donut" ? "58%" : 0}
        outerRadius="82%"
        paddingAngle={2}
        stroke="transparent"
      >
        {data.segments.map((s, i) => (
          <Cell key={i} fill={s.color} />
        ))}
      </Pie>
    </RPieChart>
  );
}
