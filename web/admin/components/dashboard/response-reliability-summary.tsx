"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { AlertTriangle, MessageSquare, Mic2 } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ChartItem } from "@/components/dashboard/resizable-chart-grid";
import { authenticatedFetcher } from "@/hooks/useAuthToken";
import type {
  ResponseReliabilityPayload,
  ResponseReliabilitySeries,
} from "@/lib/response-reliability";

const tooltipStyle = {
  backgroundColor: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "8px",
};

const formatRate = (value: number | null | undefined) =>
  value == null ? "N/A" : `${value.toFixed(1)}%`;

const formatSeconds = (value: number | null | undefined) =>
  value == null
    ? "N/A"
    : value < 60
      ? `${value.toFixed(1)}s`
      : `${(value / 60).toFixed(1)}m`;

const formatDay = (value: string) =>
  new Date(`${value}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

function ChannelReliabilityChart({
  data,
}: {
  data: ResponseReliabilitySeries;
}) {
  const chat = data.summary.chat;
  const voice = data.summary.voice;
  const failures = (chat?.failure ?? 0) + (voice?.failure ?? 0);
  const hasData = data.daily.some(
    (point) => point.chatSuccessRate != null || point.voiceSuccessRate != null,
  );

  return (
    <div className="flex h-full min-w-0 flex-col gap-2">
      <div
        className="grid divide-x border-y py-2 text-xs"
        style={{ gridTemplateColumns: "repeat(3, minmax(0, 1fr))" }}
      >
        <div className="pr-3">
          <span className="text-muted-foreground">Chat success</span>
          <div className="mt-0.5 font-semibold tabular-nums">
            {formatRate(chat?.successRate)} · avg{" "}
            {formatSeconds(chat?.averageFullAnswerSeconds)}
          </div>
        </div>
        <div className="px-3">
          <span className="text-muted-foreground">Voice success</span>
          <div className="mt-0.5 font-semibold tabular-nums">
            {formatRate(voice?.successRate)} · avg{" "}
            {formatSeconds(voice?.averageFullAnswerSeconds)}
          </div>
        </div>
        <div className="pl-3">
          <span className="text-muted-foreground">Failures</span>
          <div
            className={`mt-0.5 font-semibold tabular-nums ${failures > 0 ? "text-red-600" : ""}`}
          >
            {failures.toLocaleString()}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {hasData ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data.daily}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDay}
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
                minTickGap={24}
              />
              <YAxis
                domain={[0, 100]}
                tickFormatter={(value) => `${value}%`}
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
                width={42}
              />
              <Tooltip
                labelFormatter={(value) => formatDay(String(value))}
                formatter={(value: number, name: string) => [
                  `${Number(value).toFixed(1)}%`,
                  name,
                ]}
                contentStyle={tooltipStyle}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="chatSuccessRate"
                name="Chat success"
                stroke="#22c55e"
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="voiceSuccessRate"
                name="Voice success"
                stroke="#06b6d4"
                strokeWidth={2}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            No response telemetry for this channel yet
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Excludes cancellations and silent or too-short voice turns.
      </p>
    </div>
  );
}

export function useResponseReliabilityItems({
  token,
}: {
  token: string | null;
}): ChartItem[] {
  const { data, error, isLoading } = useSWR<ResponseReliabilityPayload>(
    token ? ["/api/omi/stats/response-reliability?days=30", token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false },
  );

  return useMemo(() => {
    const render = (channel: "production" | "beta") => {
      if (isLoading || !token) {
        return <div className="h-full animate-pulse rounded-md bg-muted/20" />;
      }
      if (error || !data?.channels) {
        return (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-red-600">
            <AlertTriangle className="h-4 w-4" /> Response reliability is
            temporarily unavailable.
          </div>
        );
      }
      return <ChannelReliabilityChart data={data.channels[channel]} />;
    };

    const subtitle = (channel: "production" | "beta") => {
      const series = data?.channels?.[channel];
      if (!series) return "Last 30 days";
      const chat = series.summary.chat;
      const voice = series.summary.voice;
      const judged =
        (chat?.success ?? 0) +
        (chat?.failure ?? 0) +
        (voice?.success ?? 0) +
        (voice?.failure ?? 0);
      return `Last 30 days · ${judged.toLocaleString()} judged responses`;
    };

    return [
      {
        id: "response-reliability-production",
        title: "Production response reliability",
        subtitle: subtitle("production"),
        icon: <MessageSquare className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 5 },
        render: () => render("production"),
      },
      {
        id: "response-reliability-beta",
        title: "Beta response reliability",
        subtitle: subtitle("beta"),
        icon: <Mic2 className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 5 },
        render: () => render("beta"),
      },
    ];
  }, [data, error, isLoading, token]);
}
