"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Bell, BellOff, Users, Send, Loader2 } from "lucide-react";
import PromptTester from "./prompt-tester";
import useSWR from "swr";
import {
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  ComposedChart,
} from "recharts";

interface DailyData {
  date: string;
  mentorSent: number;
  marketplaceMentorSent: number;
  uniqueUsersMentor: number;
  uniqueUsersMarketplace: number;
  dailyActiveUsers: number;
  dailyActiveWithMentor: number;
  enabledPct: number;
}

interface WeeklyData {
  week: string;
  mentorSent: number;
  marketplaceMentorSent: number;
  uniqueUsersMentor: number;
  uniqueUsersMarketplace: number;
}

interface HourlyData {
  hour: string; // "2026-02-19T14"
  mentor: number;
  marketplace: number;
  total: number;
}

interface NotificationStats {
  dailyData: DailyData[];
  weeklyData: WeeklyData[];
  hourlyData: HourlyData[];
  enabledDisabled: {
    enabled: number;
    disabled: number;
    total: number;
  };
}

const fetcher = (url: string) =>
  fetch(url).then((res) => {
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  });

const COLORS = {
  mentor: "#6366f1",
  marketplace: "#f59e0b",
  enabled: "#22c55e",
  disabled: "#94a3b8",
};

function formatDate(dateStr: string) {
  const d = new Date(dateStr + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatWeek(weekStr: string) {
  const d = new Date(weekStr + "T00:00:00Z");
  return "W/O " + d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatHourKey(hk: string) {
  // "2026-02-19T14" → "Feb 19 2pm"
  const d = new Date(hk + ":00:00Z");
  const mon = d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const h = d.getUTCHours();
  const hr = h === 0 ? "12am" : h === 12 ? "12pm" : h < 12 ? `${h}am` : `${h - 12}pm`;
  return `${mon} ${hr}`;
}

function formatHourTick(hk: string) {
  // Show "Feb 19" at midnight, just hour otherwise
  const d = new Date(hk + ":00:00Z");
  const h = d.getUTCHours();
  if (h === 0) return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  return "";
}

export default function NotificationsPage() {
  const [days, setDays] = useState(30);

  const { data, error, isLoading } = useSWR<NotificationStats>(
    `/api/omi/stats/notifications?days=${days}`,
    fetcher,
    { revalidateOnFocus: false }
  );

  const statsError = error || (data && (data as any).error);
  const statsReady = !isLoading && !statsError && data;

  const dailyData = data?.dailyData;
  const weeklyData = data?.weeklyData;
  const hourlyData = data?.hourlyData;
  const enabledDisabled = data?.enabledDisabled;

  // Compute summary stats (only when data is ready)
  const last7Days = dailyData?.slice(-7) ?? [];
  const totalMentorLast7 = last7Days.reduce((s, d) => s + d.mentorSent, 0);
  const totalMarketplaceLast7 = last7Days.reduce((s, d) => s + d.marketplaceMentorSent, 0);

  const pieData = enabledDisabled
    ? [
        { name: "Enabled", value: enabledDisabled.enabled, color: COLORS.enabled },
        { name: "Disabled", value: enabledDisabled.disabled, color: COLORS.disabled },
      ]
    : [];

  const dailyCombined = (dailyData ?? []).map((d) => ({
    ...d,
    totalSent: d.mentorSent + d.marketplaceMentorSent,
    totalUsers: Math.max(d.uniqueUsersMentor, d.uniqueUsersMarketplace),
  }));

  const weeklyCombined = (weeklyData ?? []).map((w) => ({
    ...w,
    totalSent: w.mentorSent + w.marketplaceMentorSent,
  }));

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Proactive Notifications</h1>
        <div className="flex gap-2">
          {[7, 14, 30, 60].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                days === d
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {/* Prompt Tester — always mounted so state is preserved */}
      <PromptTester />

      {/* Stats loading / error */}
      {isLoading && (
        <div className="flex items-center justify-center min-h-[200px]">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}
      {statsError && (
        <Card className="p-6">
          <p className="text-destructive">Failed to load notification data.</p>
          <p className="text-sm text-muted-foreground mt-1">{(data as any)?.error || error?.message}</p>
        </Card>
      )}

      {/* Summary Cards */}
      {statsReady && enabledDisabled && <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Notifications Enabled
            </CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{enabledDisabled.enabled.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              of {enabledDisabled.total.toLocaleString()} total users (
              {((enabledDisabled.enabled / enabledDisabled.total) * 100).toFixed(1)}%)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Notifications Disabled
            </CardTitle>
            <BellOff className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{enabledDisabled.disabled.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              {((enabledDisabled.disabled / enabledDisabled.total) * 100).toFixed(1)}% of users
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              "Omi says" Sent (7d)
            </CardTitle>
            <Send className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalMentorLast7.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              Built-in mentor notifications
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Marketplace Mentor (7d)
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalMarketplaceLast7.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              Marketplace "Omi Mentor" app
            </p>
          </CardContent>
        </Card>
      </div>}

      {/* Charts */}
      {statsReady && <Tabs defaultValue="daily" className="space-y-4">
        <TabsList>
          <TabsTrigger value="daily">Daily</TabsTrigger>
          <TabsTrigger value="weekly">Weekly</TabsTrigger>
        </TabsList>

        <TabsContent value="daily" className="space-y-4">
          {/* Daily Notifications Sent */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold mb-4">Daily Notifications Sent</h2>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailyCombined}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatDate}
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <Tooltip
                    labelFormatter={(label) => formatDate(label as string)}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Legend />
                  <Bar
                    dataKey="mentorSent"
                    name="Omi says (built-in)"
                    fill={COLORS.mentor}
                    radius={[2, 2, 0, 0]}
                    stackId="a"
                  />
                  <Bar
                    dataKey="marketplaceMentorSent"
                    name="Marketplace Mentor"
                    fill={COLORS.marketplace}
                    radius={[2, 2, 0, 0]}
                    stackId="a"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Hourly Timeline — last 168 hours */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold mb-1">Notifications Sent — Last 168 Hours</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Each bar = 1 hour. Dates shown at midnight UTC.
            </p>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={hourlyData} barCategoryGap={0} barGap={0}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="hour"
                    tickFormatter={formatHourTick}
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                    interval={0}
                    minTickGap={40}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <Tooltip
                    labelFormatter={(hk) => formatHourKey(hk as string)}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Legend />
                  <Bar
                    dataKey="mentor"
                    name="Omi Says"
                    fill={COLORS.mentor}
                    stackId="a"
                  />
                  <Bar
                    dataKey="marketplace"
                    name="Marketplace Mentor"
                    fill={COLORS.marketplace}
                    stackId="a"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

        </TabsContent>

        <TabsContent value="weekly" className="space-y-4">
          {/* Weekly Notifications Sent */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold mb-4">Weekly Notifications Sent</h2>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weeklyCombined}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="week"
                    tickFormatter={formatWeek}
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <Tooltip
                    labelFormatter={(label) => formatWeek(label as string)}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Legend />
                  <Bar
                    dataKey="mentorSent"
                    name="Omi says (built-in)"
                    fill={COLORS.mentor}
                    radius={[2, 2, 0, 0]}
                    stackId="a"
                  />
                  <Bar
                    dataKey="marketplaceMentorSent"
                    name="Marketplace Mentor"
                    fill={COLORS.marketplace}
                    radius={[2, 2, 0, 0]}
                    stackId="a"
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>

          {/* Weekly Unique Users */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold mb-4">Weekly Unique Users Receiving Notifications</h2>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weeklyData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="week"
                    tickFormatter={formatWeek}
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <Tooltip
                    labelFormatter={(label) => formatWeek(label as string)}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Legend />
                  <Bar
                    dataKey="uniqueUsersMentor"
                    name="Omi says (built-in)"
                    fill={COLORS.mentor}
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey="uniqueUsersMarketplace"
                    name="Marketplace Mentor"
                    fill={COLORS.marketplace}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </TabsContent>
      </Tabs>}

      {/* DAU vs Notifications Enabled */}
      {statsReady && <>
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">Daily Active Users vs Notifications Enabled</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Users who opened the app each day vs those with "Omi Says" proactive notifications enabled
        </p>
        <div className="h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={dailyData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="date"
                tickFormatter={formatDate}
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis
                yAxisId="left"
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                labelFormatter={(label) => formatDate(label as string)}
                formatter={(value: any, name: string) => {
                  if (name === "% Enabled") return [`${value}%`, name];
                  return [Number(value).toLocaleString(), name];
                }}
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                }}
              />
              <Legend />
              <Bar
                yAxisId="left"
                dataKey="dailyActiveUsers"
                name="Opened App"
                fill="#e2e8f0"
                radius={[2, 2, 0, 0]}
              />
              <Bar
                yAxisId="left"
                dataKey="dailyActiveWithMentor"
                name="Notifications Enabled"
                fill={COLORS.enabled}
                radius={[2, 2, 0, 0]}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="enabledPct"
                name="% Enabled"
                stroke="#8b5cf6"
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Enabled/Disabled Pie Chart */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Notification Adoption</h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(1)}%`}
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: any) => Number(value).toLocaleString()}
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-col justify-center space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS.enabled }} />
              <div>
                <p className="font-medium">Enabled</p>
                <p className="text-sm text-muted-foreground">
                  {enabledDisabled!.enabled.toLocaleString()} users have "Omi Says" notifications on
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS.disabled }} />
              <div>
                <p className="font-medium">Disabled / Never Set</p>
                <p className="text-sm text-muted-foreground">
                  {enabledDisabled!.disabled.toLocaleString()} users (includes default-off users)
                </p>
              </div>
            </div>
            <div className="pt-2 border-t">
              <p className="text-sm text-muted-foreground">
                Note: Notification click tracking is not yet implemented. The app currently does not
                track when users tap on proactive notifications.
              </p>
            </div>
          </div>
        </div>
      </Card>
      </>}
    </div>
  );
}
