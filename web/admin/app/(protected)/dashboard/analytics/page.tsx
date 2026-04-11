"use client";

import { useState, useMemo } from "react";
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
  Monitor,
  Bell,
  BellOff,
  Send,
  MousePointerClick,
  Percent,
  AlertTriangle,
} from "lucide-react";
import useSWR from "swr";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";
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
  PieChart,
  Pie,
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
  partial?: boolean;
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
  partial?: boolean;
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

interface NotificationDailyData {
  date: string;
  mentorSent: number;
  marketplaceMentorSent: number;
  uniqueUsersMentor: number;
  uniqueUsersMarketplace: number;
}

interface NotificationWeeklyData {
  week: string;
  mentorSent: number;
  marketplaceMentorSent: number;
  uniqueUsersMentor: number;
  uniqueUsersMarketplace: number;
}

interface NotificationHourlyData {
  hour: string;
  mentor: number;
  marketplace: number;
  total: number;
}

interface NotificationStats {
  dailyData: NotificationDailyData[];
  weeklyData: NotificationWeeklyData[];
  hourlyData: NotificationHourlyData[];
  floatingBarCtr: {
    dailyData: {
      date: string;
      sent: number;
      clicked: number;
      dismissed: number;
      ctr: number;
    }[];
    summary: {
      sent: number;
      clicked: number;
      dismissed: number;
      ctr: number;
      uniqueClickers: number;
      mode: "surface_tagged" | "all_notifications_fallback";
    };
  } | null;
  enabledDisabled: {
    enabled: number;
    disabled: number;
    total: number;
  };
}

interface DauTrendsData {
  data: { date: string; dau: number }[];
  days: number;
}

interface CrashRateData {
  data: { date: string; crashes: number; users: number; crashFreeRate: number }[];
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

interface MacosVersionBreakdown {
  label: string;
  value: number;
  color: string;
}

interface MacosVersionStatsData {
  date: string;
  activeUsers: number;
  channelBreakdown: MacosVersionBreakdown[];
  versionBreakdown: MacosVersionBreakdown[];
}

// --- Helpers ---

const authFetcher = authenticatedFetcher;

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

function formatWeek(v: string): string {
  const d = new Date(v + "T00:00:00Z");
  return `W/O ${d.toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;
}

function weekStartKey(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00Z");
  const day = d.getUTCDay();
  const diff = d.getUTCDate() - day + (day === 0 ? -6 : 1);
  const weekStart = new Date(d);
  weekStart.setUTCDate(diff);
  return weekStart.toISOString().split("T")[0];
}

function formatHourKey(v: string): string {
  const d = new Date(v + ":00:00Z");
  const mon = d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const hour = d.getUTCHours();
  const label = hour === 0 ? "12am" : hour === 12 ? "12pm" : hour < 12 ? `${hour}am` : `${hour - 12}pm`;
  return `${mon} ${label}`;
}

function formatHourTick(v: string): string {
  const d = new Date(v + ":00:00Z");
  return d.getUTCHours() === 0
    ? d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" })
    : "";
}

const tooltipStyle = {
  backgroundColor: "hsl(var(--card))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "8px",
};

// --- Component ---

export default function AnalyticsPage() {
  const { token } = useAuthToken();
  const [months, setMonths] = useState(12);
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

  const { data: notificationStats, isLoading: notificationStatsLoading } =
    useSWR<NotificationStats>(token ? ["/api/omi/stats/notifications?days=30", token] : null, authFetcher, swrOpts);

  const { data: viralMetrics, isLoading: viralLoading } =
    useSWR<ViralMetrics>(token ? ["/api/omi/stats/viral-metrics?days=60", token] : null, authFetcher, swrOpts);

  const { data: macosVersionStats, isLoading: macosVersionStatsLoading } =
    useSWR<MacosVersionStatsData>(token ? ["/api/omi/stats/macos-versions", token] : null, authFetcher, swrOpts);

  const { data: crashRate, isLoading: crashRateLoading } =
    useSWR<CrashRateData>(token ? ["/api/omi/stats/crash-rate?days=30", token] : null, authFetcher, swrOpts);

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
  const hasPartialData = !!(revenue?.partial || subCounts?.partial || (mrrTrends as any)?.partial || (subTrends as any)?.partial);
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
  const notificationDailyData = notificationStats?.dailyData ?? [];
  const notificationWeeklyData = notificationStats?.weeklyData ?? [];
  const notificationHourlyData = notificationStats?.hourlyData ?? [];
  const notificationEnabledDisabled = notificationStats?.enabledDisabled;
  const floatingBarCtr = notificationStats?.floatingBarCtr;
  const macosChannelData = macosVersionStats?.channelBreakdown ?? [];
  const macosVersionData = macosVersionStats?.versionBreakdown ?? [];
  const notificationLast7Days = notificationDailyData.slice(-7);
  const notificationMentorLast7 = notificationLast7Days.reduce((sum, day) => sum + day.mentorSent, 0);
  const notificationMarketplaceLast7 = notificationLast7Days.reduce((sum, day) => sum + day.marketplaceMentorSent, 0);
  const floatingBarCtrSummary = floatingBarCtr?.summary;
  const notificationDailyCombined = notificationDailyData.map((day) => ({
    ...day,
    totalSent: day.mentorSent + day.marketplaceMentorSent,
    totalUsers: Math.max(day.uniqueUsersMentor, day.uniqueUsersMarketplace),
  }));
  const notificationWeeklyCombined = notificationWeeklyData.map((week) => ({
    ...week,
    totalSent: week.mentorSent + week.marketplaceMentorSent,
    totalUniqueUsers: week.uniqueUsersMentor + week.uniqueUsersMarketplace,
  }));
  const weeklyRatingsData = useMemo(() => {
    const buckets = new Map<string, { thumbs_up: number; thumbs_down: number }>();
    for (const point of ratingsData) {
      const key = weekStartKey(point.date);
      const bucket = buckets.get(key) ?? { thumbs_up: 0, thumbs_down: 0 };
      bucket.thumbs_up += point.thumbs_up;
      bucket.thumbs_down += point.thumbs_down;
      buckets.set(key, bucket);
    }

    return Array.from(buckets.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([week, counts]) => {
        const total = counts.thumbs_up + counts.thumbs_down;
        return {
          week,
          thumbs_up: counts.thumbs_up,
          thumbs_down: counts.thumbs_down,
          ratio: total > 0 ? Math.round((counts.thumbs_up / total) * 100) : 0,
        };
      });
  }, [ratingsData]);

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
      {hasPartialData && (
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Some data sources failed to load. Numbers may be incomplete.</span>
        </div>
      )}
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
          <div>
            <h2 className="text-lg font-semibold">macOS Active Versions</h2>
            <p className="text-sm text-muted-foreground">
              Active users for {macosVersionStats?.date ?? "today"}, split by release channel and app version
            </p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold">{macosVersionStats?.activeUsers?.toLocaleString() ?? "--"}</div>
            <p className="text-xs text-muted-foreground">active macOS users today</p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">Beta vs Production</h3>
            <div className="h-[280px]">
              {macosVersionStatsLoading ? (
                <div className="h-full flex items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : macosChannelData.length === 0 ? (
                <div className="h-full flex items-center justify-center text-muted-foreground">
                  No active-user channel data yet
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={macosChannelData}
                      cx="50%"
                      cy="50%"
                      innerRadius={65}
                      outerRadius={105}
                      paddingAngle={3}
                      dataKey="value"
                      nameKey="label"
                      label={({ label, percent }) => `${label} ${(percent * 100).toFixed(0)}%`}
                    >
                      {macosChannelData.map((entry) => (
                        <Cell key={entry.label} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number, _name, entry: { payload?: MacosVersionBreakdown }) => [
                        Number(value).toLocaleString(),
                        entry?.payload?.label ?? "Users",
                      ]}
                      contentStyle={tooltipStyle}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">By Version</h3>
            <div className="h-[280px]">
              {macosVersionStatsLoading ? (
                <div className="h-full flex items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : macosVersionData.length === 0 ? (
                <div className="h-full flex items-center justify-center text-muted-foreground">
                  No active-user version data yet
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={macosVersionData}
                      cx="50%"
                      cy="50%"
                      innerRadius={65}
                      outerRadius={105}
                      paddingAngle={2}
                      dataKey="value"
                      nameKey="label"
                    >
                      {macosVersionData.map((entry) => (
                        <Cell key={entry.label} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: number, _name, entry: { payload?: MacosVersionBreakdown }) => [
                        Number(value).toLocaleString(),
                        entry?.payload?.label ?? "Version",
                      ]}
                      contentStyle={tooltipStyle}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] mt-4">
          <div className="rounded-lg border p-4">
            <div className="flex items-center gap-2 mb-3">
              <Monitor className="h-4 w-4 text-muted-foreground" />
              <h3 className="font-medium">Channel Counts</h3>
            </div>
            <div className="space-y-3">
              {macosChannelData.map((entry) => (
                <div key={entry.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: entry.color }} />
                    <span className="text-sm">{entry.label}</span>
                  </div>
                  <span className="text-sm font-medium">{entry.value.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border p-4">
            <h3 className="font-medium mb-3">Version Counts</h3>
            <div className="space-y-3 max-h-[220px] overflow-y-auto pr-1">
              {macosVersionData.map((entry) => (
                <div key={entry.label} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: entry.color }} />
                    <span className="text-sm">{entry.label}</span>
                  </div>
                  <span className="text-sm font-medium">{entry.value.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Floating Bar Sessions per User */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Floating Bar Sessions per User</h2>
          {fbSummary && (
            <span className="text-sm text-muted-foreground">
              Avg: <span className="font-medium text-foreground">{fbSummary.overallAvgPerUserPerDay ?? "—"}</span> sessions/user/day
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

      <h2 className="text-2xl font-bold tracking-tight pt-4">Notification Analytics</h2>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Notifications Enabled</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{notificationEnabledDisabled?.enabled?.toLocaleString() ?? "--"}</div>
            <p className="text-xs text-muted-foreground">
              {notificationEnabledDisabled
                ? `of ${notificationEnabledDisabled.total.toLocaleString()} users (${((notificationEnabledDisabled.enabled / notificationEnabledDisabled.total) * 100).toFixed(1)}%)`
                : "Loading notification adoption"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Notifications Disabled</CardTitle>
            <BellOff className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{notificationEnabledDisabled?.disabled?.toLocaleString() ?? "--"}</div>
            <p className="text-xs text-muted-foreground">Explicitly disabled desktop notifications</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">"Omi says" Sent (7d)</CardTitle>
            <Send className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{notificationMentorLast7.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Built-in mentor notifications</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Marketplace Mentor (7d)</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{notificationMarketplaceLast7.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">Marketplace "Omi Mentor" app</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Floating Bar Clicks</CardTitle>
            <MousePointerClick className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{floatingBarCtrSummary?.clicked?.toLocaleString() ?? "0"}</div>
            <p className="text-xs text-muted-foreground">Explicit notification opens from the floating bar</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Floating Bar CTR</CardTitle>
            <Percent className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{floatingBarCtrSummary ? `${floatingBarCtrSummary.ctr.toFixed(1)}%` : "0.0%"}</div>
            <p className="text-xs text-muted-foreground">
              {floatingBarCtrSummary
                ? floatingBarCtrSummary.mode === "surface_tagged"
                  ? `${floatingBarCtrSummary.sent.toLocaleString()} tagged sends, ${floatingBarCtrSummary.uniqueClickers.toLocaleString()} unique clickers`
                  : `Fallback: all desktop notifications, ${floatingBarCtrSummary.sent.toLocaleString()} sent`
                : "Waiting for new surface-tagged events"}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-4">Daily Notifications Sent</h2>
        <div className="h-[350px]">
          {notificationStatsLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={notificationDailyCombined}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" tickFormatter={shortDate} className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip labelFormatter={fullDate} contentStyle={tooltipStyle} />
                <Legend />
                <Bar dataKey="mentorSent" name="Omi says (built-in)" fill="#6366f1" radius={[2, 2, 0, 0]} stackId="a" />
                <Bar dataKey="marketplaceMentorSent" name="Marketplace Mentor" fill="#f59e0b" radius={[2, 2, 0, 0]} stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Notifications Sent, Last 168 Hours</h2>
          <p className="text-sm text-muted-foreground mb-4">Hourly volume, with dates marked at midnight UTC.</p>
          <div className="h-[320px]">
            {notificationStatsLoading ? (
              <div className="h-full flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={notificationHourlyData} barCategoryGap={0} barGap={0}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="hour" tickFormatter={formatHourTick} className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} interval={0} minTickGap={40} />
                  <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip labelFormatter={(value) => formatHourKey(value as string)} contentStyle={tooltipStyle} />
                  <Legend />
                  <Bar dataKey="mentor" name="Omi Says" fill="#6366f1" stackId="a" />
                  <Bar dataKey="marketplace" name="Marketplace Mentor" fill="#f59e0b" stackId="a" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Floating Bar Notification CTR</h2>
          <p className="text-sm text-muted-foreground mb-4">
            {floatingBarCtrSummary?.mode === "surface_tagged"
              ? "Sent vs clicked proactive notifications in the desktop floating bar."
              : "Surface-tagged floating-bar events are not populated yet, so this is currently using all desktop notification clicks as a fallback."}
          </p>
          <div className="h-[320px]">
            {notificationStatsLoading ? (
              <div className="h-full flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={floatingBarCtr?.dailyData ?? []}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" tickFormatter={shortDate} className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis yAxisId="left" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis yAxisId="right" orientation="right" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    labelFormatter={fullDate}
                    formatter={(value: number, name: string) => name === "CTR" ? [`${value}%`, name] : [value.toLocaleString(), name]}
                    contentStyle={tooltipStyle}
                  />
                  <Legend />
                  <Bar yAxisId="left" dataKey="sent" name="Sent" fill="#6366f1" radius={[2, 2, 0, 0]} />
                  <Bar yAxisId="left" dataKey="clicked" name="Clicked" fill="#22c55e" radius={[2, 2, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="ctr" name="CTR" stroke="#f59e0b" strokeWidth={2} dot={{ r: 3 }} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Weekly Notification Reach</h2>
          <p className="text-sm text-muted-foreground mb-4">Volume and unique recipients in one view.</p>
          <div className="h-[320px]">
            {notificationStatsLoading ? (
              <div className="h-full flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={notificationWeeklyCombined}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="week" tickFormatter={formatWeek} className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis yAxisId="left" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis yAxisId="right" orientation="right" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip labelFormatter={formatWeek} contentStyle={tooltipStyle} />
                  <Legend />
                  <Bar yAxisId="left" dataKey="mentorSent" name="Omi says sent" fill="#6366f1" radius={[2, 2, 0, 0]} stackId="a" />
                  <Bar yAxisId="left" dataKey="marketplaceMentorSent" name="Marketplace sent" fill="#f59e0b" radius={[2, 2, 0, 0]} stackId="a" />
                  <Line yAxisId="right" type="monotone" dataKey="uniqueUsersMentor" name="Omi says unique users" stroke="#a78bfa" strokeWidth={2} dot={false} />
                  <Line yAxisId="right" type="monotone" dataKey="uniqueUsersMarketplace" name="Marketplace unique users" stroke="#fbbf24" strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <h2 className="text-lg font-semibold mb-1">Notification Settings</h2>
          <p className="text-sm text-muted-foreground mb-4">
            Based on the desktop <code className="text-xs">notifications_enabled</code> toggle. Missing values default to enabled.
          </p>
          <div className="space-y-4">
            <div className="rounded-lg border border-border/60 bg-muted/20 p-4">
              <div className="flex items-end justify-between gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">Enabled share</div>
                  <div className="text-3xl font-semibold">
                    {notificationEnabledDisabled ? `${((notificationEnabledDisabled.enabled / notificationEnabledDisabled.total) * 100).toFixed(1)}%` : "--"}
                  </div>
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  <div>{notificationEnabledDisabled?.enabled?.toLocaleString() ?? "--"} enabled</div>
                  <div>{notificationEnabledDisabled?.disabled?.toLocaleString() ?? "--"} disabled</div>
                </div>
              </div>
              <div className="mt-4 h-3 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-green-500"
                  style={{
                    width: notificationEnabledDisabled
                      ? `${(notificationEnabledDisabled.enabled / notificationEnabledDisabled.total) * 100}%`
                      : "0%",
                  }}
                />
              </div>
            </div>
          </div>
        </Card>
      </div>

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
          Weekly thumbs up/down from macOS floating bar. The overall positive rate is shown above.
        </p>
        <div className="h-[300px]">
          {ratingsLoading ? (
            <div className="h-full flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : weeklyRatingsData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-muted-foreground">
              No rating data yet
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={weeklyRatingsData}>
                <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
                <XAxis
                  dataKey="week"
                  tickFormatter={formatWeek}
                  tick={{ fontSize: 11 }}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={formatWeek}
                  formatter={(value: number, name: string) => [value, name === "thumbs_up" ? "Thumbs Up" : "Thumbs Down"]}
                />
                <Legend />
                <Bar dataKey="thumbs_up" name="Thumbs Up" fill="#22c55e" radius={[2, 2, 0, 0]} />
                <Bar dataKey="thumbs_down" name="Thumbs Down" fill="#ef4444" radius={[2, 2, 0, 0]} />
              </BarChart>
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

      {/* Crash Rate */}
      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">App Stability</h2>
          {crashRate?.data && (() => {
            const recent = crashRate.data.slice(-7);
            const totalCrashes = recent.reduce((s, d) => s + d.crashes, 0);
            const totalUsers = recent.reduce((s, d) => s + d.users, 0);
            const rate = totalUsers > 0 ? ((1 - totalCrashes / totalUsers) * 100).toFixed(1) : "100.0";
            return (
              <span className="text-sm text-muted-foreground">
                {rate}% crash-free (7d) · {totalCrashes} crashes
              </span>
            );
          })()}
        </div>
        <p className="text-sm text-muted-foreground mb-4">Daily crashes vs active users (last 30 days)</p>
        <div className="h-[300px]">
          {crashRateLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (crashRate?.data?.length ?? 0) > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={crashRate!.data}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} />
                <YAxis yAxisId="left" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <YAxis yAxisId="right" orientation="right" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}%`} domain={[90, 100]} />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    if (name === "crashFreeRate") return [`${value}%`, "Crash-Free Rate"];
                    if (name === "crashes") return [value.toLocaleString(), "Crashes"];
                    return [value.toLocaleString(), "Active Users"];
                  }}
                  labelFormatter={fullDate}
                  contentStyle={tooltipStyle}
                />
                <Legend />
                <Bar yAxisId="left" dataKey="crashes" name="Crashes" fill="#ef4444" radius={[2, 2, 0, 0]} />
                <Bar yAxisId="left" dataKey="users" name="Active Users" fill="#6366f1" radius={[2, 2, 0, 0]} opacity={0.3} />
                <Line yAxisId="right" type="monotone" dataKey="crashFreeRate" name="Crash-Free Rate" stroke="#22c55e" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No crash data yet — events will appear after v0.11.277+
            </div>
          )}
        </div>
      </Card>

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
      {/* Chat Ratings by Week */}
      <ChatRatingsChart token={token} />
    </div>
  );
}

// --- Chat Ratings Chart (Firebase analytics collection) ---

interface RatingWeek { week: string; thumbs_up: number; thumbs_down: number }
interface RatingVersion { version: string; thumbs_up: number; thumbs_down: number }
interface ChatRatingsWeekData { weeks: RatingWeek[]; total_up: number; total_down: number }
interface ChatRatingsVersionData { versions: RatingVersion[]; total_up: number; total_down: number }

function ChatRatingsChart({ token }: { token: string | null }) {
  const [platform, setPlatform] = useState<"all" | "desktop" | "mobile">("desktop");
  const [groupBy, setGroupBy] = useState<"week" | "version">("week");

  const { data: weekData, isLoading: weekLoading } = useSWR<ChatRatingsWeekData>(
    token && groupBy === "week" ? [`/api/omi/chat-lab/ratings?platform=${platform}&group_by=week`, token] : null,
    authenticatedFetcher
  );
  const { data: versionData, isLoading: versionLoading } = useSWR<ChatRatingsVersionData>(
    token && groupBy === "version" ? [`/api/omi/chat-lab/ratings?platform=${platform}&group_by=version`, token] : null,
    authenticatedFetcher
  );

  const isLoading = groupBy === "week" ? weekLoading : versionLoading;

  const stats = useMemo(() => {
    const d = groupBy === "week" ? weekData : versionData;
    if (!d) return { total: 0, up: 0, down: 0, pct: 0 };
    const { total_up: up, total_down: down } = d;
    const total = up + down;
    return { total, up, down, pct: total > 0 ? Math.round((up / total) * 100) : 0 };
  }, [weekData, versionData, groupBy]);

  const chartData = useMemo(() => {
    if (groupBy === "version") {
      if (!versionData?.versions) return [];
      return versionData.versions
        .filter((v) => v.version !== "unknown")
        .map((v) => ({
          ...v, label: v.version.replace("0.11.", "v"),
          satisfaction: v.thumbs_up + v.thumbs_down > 0 ? Math.round((v.thumbs_up / (v.thumbs_up + v.thumbs_down)) * 100) : 0,
        }));
    }
    if (!weekData?.weeks) return [];
    return weekData.weeks.map((w) => ({
      ...w, label: w.week,
      satisfaction: w.thumbs_up + w.thumbs_down > 0 ? Math.round((w.thumbs_up / (w.thumbs_up + w.thumbs_down)) * 100) : 0,
    }));
  }, [weekData, versionData, groupBy]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span>Chat Response Ratings</span>
            <div className="flex rounded-md overflow-hidden border border-border text-xs font-medium">
              {(["all", "desktop", "mobile"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => setPlatform(p)}
                  className={`px-3 py-1 transition-colors ${
                    platform === p
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {p === "all" ? "All" : p === "desktop" ? "Desktop" : "Mobile"}
                </button>
              ))}
            </div>
            <div className="flex rounded-md overflow-hidden border border-border text-xs font-medium">
              {(["week", "version"] as const).map((g) => (
                <button key={g} onClick={() => setGroupBy(g)}
                  className={`px-3 py-1 transition-colors ${groupBy === g ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:bg-accent"}`}
                >{g === "week" ? "By Week" : "By Version"}</button>
              ))}
            </div>
          </div>
          {stats.total > 0 && (
            <div className="flex items-center gap-4 text-sm font-normal">
              <span className="text-green-500">{stats.up} 👍</span>
              <span className="text-red-500">{stats.down} 👎</span>
              <span className={`font-bold ${stats.pct >= 60 ? "text-green-500" : stats.pct >= 40 ? "text-yellow-500" : "text-red-500"}`}>
                {stats.pct}% positive
              </span>
            </div>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center h-[200px] text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading ratings...
          </div>
        ) : !chartData.length ? (
          <div className="text-center text-muted-foreground py-12">
            {groupBy === "version"
              ? "No version-tagged ratings yet. Ratings will be tagged with app version after the next desktop release."
              : "No chat ratings data available"}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="count" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="pct" orientation="right" tick={{ fontSize: 11 }} domain={[0, 100]} unit="%" />
              <Tooltip
                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: 8 }}
                labelStyle={{ color: "#ccc" }}
              />
              <Legend />
              <Bar yAxisId="count" dataKey="thumbs_up" name="👍 Likes" fill="#22c55e" radius={[4, 4, 0, 0]} />
              <Bar yAxisId="count" dataKey="thumbs_down" name="👎 Dislikes" fill="#ef4444" radius={[4, 4, 0, 0]} />
              <Line yAxisId="pct" dataKey="satisfaction" name="Satisfaction %" stroke="#a855f7" strokeWidth={2} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
