"use client";

import { useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DollarSign,
  TrendingUp,
  Users,
  MessageSquare,
  Loader2,
  Activity,
  Zap,
  Target,
  BarChart3,
} from "lucide-react";
import useSWR from "swr";
import { useAuth } from "@/components/auth-provider";
import {
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  LineChart,
  Area,
  AreaChart,
  ComposedChart,
  ReferenceLine,
  Cell,
} from "recharts";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// --- Types ---

interface RevenueData {
  mrr: number;
  arr: number;
}

interface MrrTrendPoint {
  month: string;
  monthKey: string;
  mrr: number;
}

interface SubscriptionTrendPoint {
  month: string;
  monthKey: string;
  monthly: number;
  annual: number;
}

interface SubscriptionCounts {
  totalSubscriptions: number;
  priceIdOne: { count: number; priceId: string };
  priceIdTwo: { count: number; priceId: string };
}

interface ConversationCount {
  totalConversations: number;
}

interface RetentionPoint {
  day: number;
  retention: number;
}

interface CohortData {
  date: string;
  users: number;
  data: RetentionPoint[];
}

interface RetentionData {
  data: RetentionPoint[];
  cohorts: CohortData[];
  totalCohorts: number;
  totalUsers: number;
}

interface DailyNewUsersData {
  data: { date: string; users: number; cumulative: number }[];
  totalUsers: number;
  days: number;
}

interface MessageRatingsData {
  data: { date: string; thumbs_up: number; thumbs_down: number; ratio: number }[];
  days: number;
}

interface FloatingBarUsageData {
  data: {
    date: string;
    total_queries: number;
    text_queries: number;
    voice_queries: number;
    unique_users: number;
    avg_per_user: number;
  }[];
  days: number;
  summary: {
    totalQueries: number;
    totalVoice: number;
    totalText: number;
    overallAvgPerUserPerDay: number;
    activeDays: number;
  };
}

interface DauTrendsData {
  data: { date: string; dau: number }[];
  days: number;
}

interface ViralMetrics {
  growthAccounting: {
    week: string;
    active: number;
    newUsers: number;
    retained: number;
    resurrected: number;
    churned: number;
  }[];
  stickinessTrend: {
    week: string;
    avgDau: number;
    wau: number;
    dauWau: number;
  }[];
  dailyDau: { date: string; dau: number }[];
  powerUserCurve: { daysActive: number; users: number; pct: number }[];
  activation: { date: string; signups: number; activated: number; rate: number }[];
  summary: {
    quickRatio: number | null;
    activationRate: number | null;
    dauMau: number;
    dauWau: number;
    dau: number;
    wau: number;
    mau: number;
    l5PlusPct: number;
    totalUsers: number;
  };
}

// --- Helpers ---

const authFetcher = async ([url, token]: [string, string | null]) => {
  if (!token) throw new Error("Auth token not available");
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
};

const COLORS = {
  mrr: "#6366f1",
  monthly: "#6366f1",
  annual: "#22c55e",
  area: "#6366f1",
};

function retentionHeatColor(pct: number): string {
  const alpha = Math.min(pct / 100, 1);
  return `rgba(99, 102, 241, ${(alpha * 0.7 + 0.05).toFixed(2)})`;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function formatCompact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString();
}

function formatCohortDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function shortDate(v: string): string {
  const d = new Date(v + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function fullDate(v: string): string {
  const d = new Date(v + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

const tooltipStyle = {
  backgroundColor: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "8px",
};

// --- Component ---

export default function AnalyticsPage() {
  const { user } = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [months, setMonths] = useState(12);

  useEffect(() => {
    if (user) {
      user.getIdToken().then(setToken).catch(() => setToken(null));
    }
  }, [user]);
  const [retentionDays, setRetentionDays] = useState(30);
  const [retentionPlatform, setRetentionPlatform] = useState("macos");
  const [retentionView, setRetentionView] = useState<"average" | "cohorts">("average");

  const swrOpts = { revalidateOnFocus: false };

  const { data: revenue, isLoading: revenueLoading, error: revenueError } = useSWR<RevenueData>(
    token ? ["/api/omi/stats/revenue", token] : null, authFetcher, swrOpts
  );

  const { data: mrrTrends, isLoading: mrrLoading, error: mrrError } = useSWR<{
    data: MrrTrendPoint[];
  }>(token ? [`/api/omi/stats/mrr-trends?months=${months}`, token] : null, authFetcher, swrOpts);

  const { data: subTrends, isLoading: subTrendsLoading, error: subTrendsError } = useSWR<{
    data: SubscriptionTrendPoint[];
  }>(token ? [`/api/omi/stats/subscription-trends?months=${months}`, token] : null, authFetcher, swrOpts);

  const { data: subCounts, isLoading: subCountsLoading, error: subCountsError } =
    useSWR<SubscriptionCounts>(token ? ["/api/omi/stats/subscriptions", token] : null, authFetcher, swrOpts);

  const { data: convCount, isLoading: convLoading, error: convError } =
    useSWR<ConversationCount>(token ? ["/api/omi/stats/conversation-count", token] : null, authFetcher, swrOpts);

  const { data: dailyNewUsers, isLoading: dailyNewUsersLoading } =
    useSWR<DailyNewUsersData>(token ? ["/api/omi/stats/daily-new-users?days=60", token] : null, authFetcher, swrOpts);

  const { data: dauTrends, isLoading: dauLoading } =
    useSWR<DauTrendsData>(token ? ["/api/omi/stats/dau-trends?days=60", token] : null, authFetcher, swrOpts);

  const { data: messageRatings, isLoading: ratingsLoading } =
    useSWR<MessageRatingsData>(token ? ["/api/omi/stats/message-ratings?days=30", token] : null, authFetcher, swrOpts);

  const { data: floatingBarUsage, isLoading: fbUsageLoading } =
    useSWR<FloatingBarUsageData>(token ? ["/api/omi/stats/floating-bar-usage?days=30", token] : null, authFetcher, swrOpts);

  const { data: viralMetrics, isLoading: viralLoading } =
    useSWR<ViralMetrics>(token ? ["/api/omi/stats/viral-metrics?days=60", token] : null, authFetcher, swrOpts);

  const retentionPlatformParam = retentionPlatform ? `&platform=${retentionPlatform}` : '';

  const { data: mixpanelRetention, isLoading: mixpanelRetLoading } =
    useSWR<RetentionData>(
      token ? [`/api/omi/stats/retention/mixpanel?days=${retentionDays}${retentionPlatformParam}`, token] : null,
      authFetcher, swrOpts
    );

  const isLoading =
    revenueLoading ||
    mrrLoading ||
    subTrendsLoading ||
    subCountsLoading ||
    convLoading;

  const hasError = revenueError || mrrError || subTrendsError || subCountsError || convError;

  const mrr = revenue?.mrr ?? 0;
  const arr = revenue?.arr ?? 0;
  const totalSubs = subCounts?.totalSubscriptions ?? 0;
  const monthlySubs = subCounts?.priceIdOne?.count ?? 0;
  const annualSubs = subCounts?.priceIdTwo?.count ?? 0;
  const totalConversations = convCount?.totalConversations ?? 0;
  const mrrData = mrrTrends?.data ?? [];
  const subData = subTrends?.data ?? [];

  let mrrGrowthPct: number | null = null;
  if (mrrData.length >= 2) {
    const current = mrrData[mrrData.length - 1].mrr;
    const previous = mrrData[mrrData.length - 2].mrr;
    if (previous > 0) {
      mrrGrowthPct = ((current - previous) / previous) * 100;
    }
  }

  const cohorts = mixpanelRetention?.cohorts ?? [];
  let cohortMaxDays = 0;
  for (const c of cohorts) {
    if (c.data.length > cohortMaxDays) cohortMaxDays = c.data.length;
  }

  const allDailyData = dailyNewUsers?.data ?? [];
  const dailyData = allDailyData.slice(-30);
  const dauData = dauTrends?.data?.slice(-30) ?? [];
  const ratingsData = messageRatings?.data ?? [];
  const totalThumbsUp = ratingsData.reduce((s, d) => s + d.thumbs_up, 0);
  const totalThumbsDown = ratingsData.reduce((s, d) => s + d.thumbs_down, 0);
  const totalRatings = totalThumbsUp + totalThumbsDown;
  const overallRatio = totalRatings > 0 ? Math.round((totalThumbsUp / totalRatings) * 100) : 0;
  const fbUsageData = floatingBarUsage?.data ?? [];
  const fbSummary = floatingBarUsage?.summary;

  // 7-day rolling average for daily new users
  const dailyWithRollingAvg = useMemo(() => {
    return allDailyData.map((point, i) => {
      if (i < 6) return { ...point, rollingAvg: undefined };
      const slice = allDailyData.slice(i - 6, i + 1);
      const avg = slice.reduce((s, p) => s + p.users, 0) / 7;
      return { ...point, rollingAvg: Math.round(avg * 10) / 10 };
    }).slice(-30);
  }, [allDailyData]);

  // Retention values for summary cards
  const retentionD1 = mixpanelRetention?.data?.find((p) => p.day === 1)?.retention ?? null;
  const retentionD7 = mixpanelRetention?.data?.find((p) => p.day === 7)?.retention ?? null;

  // Viral metrics
  const vm = viralMetrics;
  const ga = vm?.growthAccounting ?? [];
  const powerCurve = vm?.powerUserCurve ?? [];
  const activationData = vm?.activation ?? [];
  const stickinessData = vm?.stickinessTrend ?? [];

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">
          Analytics Dashboard
        </h1>
        <div className="flex gap-2">
          {[6, 12, 24].map((m) => (
            <button
              key={m}
              onClick={() => setMonths(m)}
              className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
                months === m
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-accent"
              }`}
            >
              {m}mo
            </button>
          ))}
        </div>
      </div>

      {hasError && (
        <Card className="p-4 border-destructive/50 bg-destructive/5">
          <p className="text-sm text-destructive">Some data failed to load. Showing available data.</p>
        </Card>
      )}

      {/* Revenue Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">MRR</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(mrr)}</div>
            {mrrGrowthPct !== null && (
              <p className={`text-xs ${mrrGrowthPct >= 0 ? "text-green-600" : "text-red-600"}`}>
                {mrrGrowthPct >= 0 ? "+" : ""}{mrrGrowthPct.toFixed(1)}% from last month
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">ARR</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(arr)}</div>
            <p className="text-xs text-muted-foreground">Based on current MRR</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Subscriptions</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalSubs.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              {monthlySubs} monthly &middot; {annualSubs} annual
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Conversations</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCompact(totalConversations)}</div>
            <p className="text-xs text-muted-foreground">All time</p>
          </CardContent>
        </Card>
      </div>

      {/* MRR Trend */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">MRR Over Time</h2>
        <p className="text-sm text-muted-foreground mb-4">Monthly recurring revenue from Stripe</p>
        <div className="h-[350px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={mrrData}>
              <defs>
                <linearGradient id="mrrGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLORS.area} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={COLORS.area} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="month" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${formatCompact(v)}`} />
              <Tooltip formatter={(value: number) => [formatCurrency(value), "MRR"]} contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="mrr" stroke={COLORS.mrr} strokeWidth={2} fill="url(#mrrGradient)" dot={{ r: 3, fill: COLORS.mrr }} activeDot={{ r: 5 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Subscription Growth */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">New Subscriptions</h2>
        <p className="text-sm text-muted-foreground mb-4">Monthly vs annual subscriptions created each month</p>
        <div className="h-[350px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={subData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="month" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Bar dataKey="monthly" name="Monthly" fill={COLORS.monthly} radius={[2, 2, 0, 0]} stackId="a" />
              <Bar dataKey="annual" name="Annual" fill={COLORS.annual} radius={[2, 2, 0, 0]} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* ─────────────────────────────────────────────────── */}
      {/* macOS Growth Metrics */}
      {/* ─────────────────────────────────────────────────── */}
      <h2 className="text-2xl font-bold tracking-tight pt-4">macOS Growth Metrics</h2>

      {/* Key Metrics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">DAU</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{vm?.summary.dau ?? "--"}</div>
            <p className="text-xs text-muted-foreground">avg last 7 days</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">WAU</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{vm?.summary.wau ?? "--"}</div>
            <p className="text-xs text-muted-foreground">last 7 days</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">MAU</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{vm?.summary.mau ?? "--"}</div>
            <p className="text-xs text-muted-foreground">last 30 days</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">DAU/MAU</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(vm?.summary.dauMau ?? 0) >= 20 ? "text-green-600" : ""}`}>
              {vm?.summary.dauMau != null ? `${vm.summary.dauMau}%` : "--"}
            </div>
            <p className="text-xs text-muted-foreground">Stickiness (good: 20%+)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Quick Ratio</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(vm?.summary.quickRatio ?? 0) >= 1 ? "text-green-600" : "text-red-600"}`}>
              {vm?.summary.quickRatio != null ? `${vm.summary.quickRatio}x` : "--"}
            </div>
            <p className="text-xs text-muted-foreground">Growing if &gt;1x</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Activation</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${(vm?.summary.activationRate ?? 0) >= 50 ? "text-green-600" : ""}`}>
              {vm?.summary.activationRate != null ? `${vm.summary.activationRate}%` : "--"}
            </div>
            <p className="text-xs text-muted-foreground">Memory within 7d</p>
          </CardContent>
        </Card>
      </div>

      {/* Floating Bar Sessions per User */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Floating Bar Sessions per User</h2>
          {fbSummary && (
            <span className="text-sm text-muted-foreground">
              Avg: <span className="font-medium text-foreground">{fbSummary.overallAvgSessionsPerUserPerDay ?? "—"}</span> sessions/user/day
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Times floating bar was opened and a question asked, per user per day (follow-ups don&apos;t count)
        </p>
        <div className="h-[300px]">
          {fbUsageLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : fbUsageData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              No usage data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={fbUsageData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }}
                  tick={{ fontSize: 11 }}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
                  }}
                />
                <Legend />
                <Line dataKey="avg_sessions_per_user" name="Sessions/User" stroke="#6366f1" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      {/* Message Ratings — macOS Floating Bar */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Chat Response Ratings</h2>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="text-green-500 font-medium">{totalThumbsUp} up</span>
            <span className="text-red-500 font-medium">{totalThumbsDown} down</span>
            <span>{overallRatio}% positive</span>
          </div>
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Daily thumbs up/down from macOS floating bar (last 30 days)
        </p>
        <div className="h-[300px]">
          {ratingsLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : ratingsData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              No rating data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={ratingsData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }}
                  tick={{ fontSize: 11 }}
                />
                <YAxis yAxisId="count" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="ratio" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  labelFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
                  }}
                  formatter={(value: number, name: string) => {
                    if (name === "ratio") return [`${value}%`, "Positive %"];
                    return [value, name === "thumbs_up" ? "Thumbs Up" : "Thumbs Down"];
                  }}
                />
                <Legend />
                <Bar yAxisId="count" dataKey="thumbs_up" name="Thumbs Up" fill="#22c55e" radius={[2, 2, 0, 0]} />
                <Bar yAxisId="count" dataKey="thumbs_down" name="Thumbs Down" fill="#ef4444" radius={[2, 2, 0, 0]} />
                <Line yAxisId="ratio" dataKey="ratio" name="ratio" stroke="#6366f1" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      {/* Floating Bar Usage — Queries per Day (Voice vs Text) */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Floating Bar Usage</h2>
          {fbSummary && (
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span>{fbSummary.totalQueries} total</span>
              <span className="text-blue-500 font-medium">{fbSummary.totalText} text</span>
              <span className="text-orange-500 font-medium">{fbSummary.totalVoice} voice</span>
            </div>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Daily queries by input type — text vs voice (last 30 days)
        </p>
        <div className="h-[300px]">
          {fbUsageLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : fbUsageData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              No usage data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={fbUsageData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }}
                  tick={{ fontSize: 11 }}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
                  }}
                />
                <Legend />
                <Bar dataKey="text_queries" name="Text" stackId="queries" fill="#6366f1" radius={[0, 0, 0, 0]} />
                <Bar dataKey="voice_queries" name="Voice" stackId="queries" fill="#f97316" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      {/* Floating Bar — Avg Queries per User per Day */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Avg Queries per User per Day</h2>
          {fbSummary && (
            <span className="text-sm text-muted-foreground">
              Overall: <span className="font-medium text-foreground">{fbSummary.overallAvgPerUserPerDay}</span> queries/user/day
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-4">
          Average floating bar queries per active user, daily (last 30 days)
        </p>
        <div className="h-[300px]">
          {fbUsageLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : fbUsageData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              No usage data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={fbUsageData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="date"
                  tickFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }}
                  tick={{ fontSize: 11 }}
                />
                <YAxis yAxisId="avg" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="users" orientation="right" tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(v) => {
                    const d = new Date(v + "T00:00:00");
                    return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
                  }}
                  formatter={(value: number, name: string) => {
                    if (name === "Avg/User") return [value, "Avg queries per user"];
                    return [value, "Active users"];
                  }}
                />
                <Legend />
                <Bar yAxisId="users" dataKey="unique_users" name="Active Users" fill="#e2e8f0" radius={[2, 2, 0, 0]} />
                <Line yAxisId="avg" dataKey="avg_per_user" name="Avg/User" stroke="#6366f1" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      {/* Growth Accounting */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">Growth Accounting</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Weekly breakdown: where do active users come from? (Churned shown as negative)
        </p>
        <div className="h-[350px]">
          {viralLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : ga.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ga} stackOffset="sign">
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="week" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip contentStyle={tooltipStyle} labelFormatter={fullDate} formatter={(value: number, name: string) => {
                  const labels: Record<string, string> = { newUsers: "New", retained: "Retained", resurrected: "Resurrected", churned: "Churned" };
                  return [Math.abs(value), labels[name] || name];
                }} />
                <Legend formatter={(value) => {
                  const labels: Record<string, string> = { newUsers: "New", retained: "Retained", resurrected: "Resurrected", churned: "Churned" };
                  return labels[value] || value;
                }} />
                <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" />
                <Bar dataKey="newUsers" stackId="a" fill="#22c55e" radius={[2, 2, 0, 0]} />
                <Bar dataKey="resurrected" stackId="a" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                <Bar dataKey="retained" stackId="a" fill="#6366f1" radius={[2, 2, 0, 0]} />
                <Bar dataKey="churned" stackId="a" fill="#ef4444" radius={[0, 0, 2, 2]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
          )}
        </div>
      </Card>

      {/* Two charts side by side: Cumulative Users + DAU */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Cumulative Total Users */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Cumulative Users</h2>
          <p className="text-sm text-muted-foreground mb-4">Total macOS users over time</p>
          <div className="h-[300px]">
            {dailyNewUsersLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : dailyData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={dailyData}>
                  <defs>
                    <linearGradient id="cumulativeGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                  <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={formatCompact} />
                  <Tooltip formatter={(value: number) => [value.toLocaleString(), "Total Users"]} labelFormatter={fullDate} contentStyle={tooltipStyle} />
                  <Area type="monotone" dataKey="cumulative" stroke="#22c55e" strokeWidth={2} fill="url(#cumulativeGradient)" dot={false} activeDot={{ r: 4 }} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
            )}
          </div>
        </Card>

        {/* Daily Active Users */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Daily Active Users</h2>
          <p className="text-sm text-muted-foreground mb-4">Unique macOS users per day</p>
          <div className="h-[300px]">
            {dauLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : dauData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dauData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                  <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip formatter={(value: number) => [value.toLocaleString(), "DAU"]} labelFormatter={fullDate} contentStyle={tooltipStyle} />
                  <Bar dataKey="dau" name="DAU" fill="#f59e0b" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
            )}
          </div>
        </Card>
      </div>

      {/* Daily New Users + Rolling Avg */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Daily New Users</h2>
          {dailyNewUsers?.totalUsers != null && (
            <span className="text-sm text-muted-foreground">
              {dailyNewUsers.totalUsers.toLocaleString()} in last {dailyNewUsers.days}d
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-4">First-time sign-ins with 7-day rolling average</p>
        <div className="h-[350px]">
          {dailyNewUsersLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : dailyWithRollingAvg.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={dailyWithRollingAvg}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip
                  formatter={(value: number, name: string) => [value.toLocaleString(), name === "rollingAvg" ? "7-Day Avg" : "New Users"]}
                  labelFormatter={fullDate}
                  contentStyle={tooltipStyle}
                />
                <Legend />
                <Bar dataKey="users" name="New Users" fill="#6366f1" radius={[2, 2, 0, 0]} />
                <Line type="monotone" dataKey="rollingAvg" name="7-Day Avg" stroke="#f97316" strokeWidth={2} dot={false} activeDot={{ r: 4 }} connectNulls={false} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
          )}
        </div>
      </Card>

      {/* Two charts side by side: Stickiness + Power Users */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* DAU/WAU Stickiness Trend */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Stickiness (DAU/WAU)</h2>
          <p className="text-sm text-muted-foreground mb-4">
            How often weekly users come back daily (good: 30%+)
          </p>
          <div className="h-[300px]">
            {viralLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : stickinessData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={stickinessData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="week" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                  <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}%`} domain={[0, "auto"]} />
                  <Tooltip formatter={(value: number) => [`${value}%`, "DAU/WAU"]} labelFormatter={(l) => `Week of ${fullDate(l)}`} contentStyle={tooltipStyle} />
                  <ReferenceLine y={30} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "Good", fill: "#22c55e", fontSize: 11 }} />
                  <Line type="monotone" dataKey="dauWau" stroke="#6366f1" strokeWidth={2} dot={{ r: 3, fill: "#6366f1" }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
            )}
          </div>
        </Card>

        {/* Power User Curve */}
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Power User Curve</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Days active per user in last 30 days (right-skew = healthy)
          </p>
          <div className="h-[300px]">
            {viralLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : powerCurve.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={powerCurve}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="daysActive" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} label={{ value: "Days Active", position: "insideBottom", offset: -5, fill: "hsl(var(--muted-foreground))", fontSize: 11 }} />
                  <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip formatter={(value: number, _: string, entry: any) => [`${value} users (${entry.payload.pct}%)`, "Users"]} labelFormatter={(l) => `${l} days active`} contentStyle={tooltipStyle} />
                  <Bar dataKey="users" radius={[2, 2, 0, 0]}>
                    {powerCurve.map((entry, index) => (
                      <Cell key={index} fill={entry.daysActive >= 20 ? "#22c55e" : entry.daysActive >= 10 ? "#3b82f6" : "#6366f1"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
            )}
          </div>
        </Card>
      </div>

      {/* Activation Rate */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">Activation Rate</h2>
        <p className="text-sm text-muted-foreground mb-4">
          % of new users who create a Memory within 7 days of signing up
        </p>
        <div className="h-[350px]">
          {viralLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : activationData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={activationData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                <YAxis yAxisId="left" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <YAxis yAxisId="right" orientation="right" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelFormatter={fullDate}
                  formatter={(value: number, name: string) => {
                    if (name === "rate") return [`${value}%`, "Activation Rate"];
                    if (name === "activated") return [value, "Activated"];
                    return [value, "Signups"];
                  }}
                />
                <Legend />
                <Bar yAxisId="left" dataKey="signups" name="Signups" fill="#6366f1" radius={[2, 2, 0, 0]} opacity={0.5} />
                <Bar yAxisId="left" dataKey="activated" name="Activated" fill="#22c55e" radius={[2, 2, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="rate" name="Activation %" stroke="#f97316" strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>
          )}
        </div>
      </Card>

      {/* ─────────────────────────────────────────────────── */}
      {/* Retention Section */}
      {/* ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-4">
        <h2 className="text-2xl font-bold tracking-tight">Retention</h2>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border border-input overflow-hidden">
            <button
              onClick={() => setRetentionView("average")}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                retentionView === "average"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              Average
            </button>
            <button
              onClick={() => setRetentionView("cohorts")}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                retentionView === "cohorts"
                  ? "bg-primary text-primary-foreground"
                  : "bg-background text-muted-foreground hover:bg-accent"
              }`}
            >
              By Cohort
            </button>
          </div>
          <Select value={retentionPlatform} onValueChange={setRetentionPlatform}>
            <SelectTrigger className="w-[130px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="macos">macOS</SelectItem>
              <SelectItem value="all">All Platforms</SelectItem>
            </SelectContent>
          </Select>
          <Select value={String(retentionDays)} onValueChange={(v) => setRetentionDays(parseInt(v, 10))}>
            <SelectTrigger className="w-[120px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="14">14 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="60">60 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Retention D1/D7 Summary */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">D1 Retention</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{retentionD1 !== null ? `${retentionD1.toFixed(1)}%` : "--"}</div>
            <p className={`text-xs ${retentionD1 !== null && retentionD1 >= 25 ? "text-green-600" : "text-muted-foreground"}`}>Good: 25%+</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">D7 Retention</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{retentionD7 !== null ? `${retentionD7.toFixed(1)}%` : "--"}</div>
            <p className={`text-xs ${retentionD7 !== null && retentionD7 >= 15 ? "text-green-600" : "text-muted-foreground"}`}>Good: 15%+</p>
          </CardContent>
        </Card>
      </div>

      {/* Retention Chart / Cohort Table */}
      {mixpanelRetLoading ? (
        <Card className="p-6">
          <div className="flex items-center justify-center h-[400px]">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </Card>
      ) : retentionView === "average" ? (
        <Card className="p-6">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">Average Retention Curve</h2>
            {mixpanelRetention?.totalUsers != null && (
              <span className="text-sm text-muted-foreground">
                {mixpanelRetention.totalCohorts} cohorts &middot; {mixpanelRetention.totalUsers.toLocaleString()} users
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mb-4">Weighted average retention across all cohorts</p>
          <div className="h-[350px]">
            {mixpanelRetention?.data && mixpanelRetention.data.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={mixpanelRetention.data}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="day" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `D${v}`} />
                  <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}%`} domain={[0, 100]} />
                  <Tooltip formatter={(value: number) => [`${value}%`, "Retention"]} labelFormatter={(label) => `Day ${label}`} contentStyle={tooltipStyle} />
                  <Line type="monotone" dataKey="retention" stroke="#f97316" strokeWidth={2} dot={{ r: 2, fill: "#f97316" }} activeDot={{ r: 5 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">No retention data available</div>
            )}
          </div>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b">
                  <th className="sticky left-0 z-10 bg-card px-4 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">Date</th>
                  <th className="px-3 py-3 text-right font-medium text-muted-foreground whitespace-nowrap">Users</th>
                  {Array.from({ length: cohortMaxDays }, (_, i) => (
                    <th key={i} className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap min-w-[64px]">
                      {i === 0 ? "< 1 Day" : `Day ${i}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {mixpanelRetention?.data && mixpanelRetention.data.length > 0 && (
                  <tr className="border-b font-semibold">
                    <td className="sticky left-0 z-10 bg-card px-4 py-2.5 whitespace-nowrap">Weighted Avg</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">{mixpanelRetention.totalUsers.toLocaleString()}</td>
                    {mixpanelRetention.data.map((p) => (
                      <td key={p.day} className="px-3 py-2.5 text-center" style={{ backgroundColor: retentionHeatColor(p.retention) }}>
                        <span className={p.retention > 50 ? "text-white" : ""}>{p.retention.toFixed(1)}%</span>
                      </td>
                    ))}
                  </tr>
                )}
                {cohorts.map((c) => (
                  <tr key={c.date} className="border-b last:border-b-0 hover:bg-muted/30">
                    <td className="sticky left-0 z-10 bg-card px-4 py-2 whitespace-nowrap">{formatCohortDate(c.date)}</td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{c.users}</td>
                    {Array.from({ length: cohortMaxDays }, (_, i) => {
                      const val = i < c.data.length ? c.data[i].retention : null;
                      return (
                        <td key={i} className="px-3 py-2 text-center" style={val !== null ? { backgroundColor: retentionHeatColor(val) } : {}}>
                          {val !== null ? <span className={val > 50 ? "text-white" : ""}>{val.toFixed(1)}%</span> : null}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
