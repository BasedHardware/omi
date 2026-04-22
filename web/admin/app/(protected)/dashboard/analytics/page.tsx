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
import {
  ResizableChartGrid,
  type ChartItem,
} from "@/components/dashboard/resizable-chart-grid";

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

interface ProfitabilityPoint {
  date: string;
  desktop: number;
  mobile: number;
  total: number;
}

interface ProfitabilityData {
  days: number;
  users: ProfitabilityPoint[];
  cumulativeUsers: ProfitabilityPoint[];
  activeUsers?: ProfitabilityPoint[];
  revenue: ProfitabilityPoint[];
  cost: ProfitabilityPoint[];
  costPerUser?: ProfitabilityPoint[];
  conversion: ProfitabilityPoint[];
  summary: {
    mrr: number;
    mrrDesktop: number;
    mrrMobile: number;
    mrrUnknown: number;
    totalNewDesktop: number;
    totalNewMobile: number;
    totalUsersDesktop: number;
    totalUsersMobile: number;
    totalUsersUnknown: number;
    totalCostUsd?: number;
    avgCostPerUserDesktop?: number;
    avgCostPerUserMobile?: number;
    assumptions: {
      desktopCostPerUser: number;
      mobileCostPerUser: number;
      overheadMonthlyUsd?: number;
      costSource?: "real" | "estimated";
    };
    partial: boolean;
    sources: {
      firebaseAuth: boolean;
      firestoreTokens: boolean;
      posthogDesktop?: boolean;
      mixpanelMobile?: boolean;
      stripeActive: boolean;
      stripeNewPaid: boolean;
      infraCosts?: boolean;
    };
  };
  generatedAt: number;
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
  const [cumulativeWindow, setCumulativeWindow] = useState<"7d" | "30d" | "all">("all");
  const [profitDays, setProfitDays] = useState<30 | 60 | 90>(30);
  const [desktopCostInput, setDesktopCostInput] = useState("1.20");
  const [mobileCostInput, setMobileCostInput] = useState("0.30");

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
    useSWR<DailyNewUsersData>(token ? ["/api/omi/stats/daily-new-users?days=all", token] : null, authFetcher, swrOpts);

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

  const profitQuery = useMemo(() => {
    const dc = parseFloat(desktopCostInput);
    const mc = parseFloat(mobileCostInput);
    const dcSafe = Number.isFinite(dc) && dc >= 0 ? dc : 1.2;
    const mcSafe = Number.isFinite(mc) && mc >= 0 ? mc : 0.3;
    return `days=${profitDays}&desktop_cost=${dcSafe}&mobile_cost=${mcSafe}`;
  }, [profitDays, desktopCostInput, mobileCostInput]);

  const { data: profitability, isLoading: profitLoading, error: profitError } =
    useSWR<ProfitabilityData>(
      token ? [`/api/omi/stats/profitability?${profitQuery}`, token] : null,
      authFetcher,
      swrOpts,
    );

  interface InfraCostsData {
    breakdown: Array<{
      service: string;
      mtdUsd: number;
      aprProjectionUsd: number;
      desktopProjectionUsd: number;
      mobileProjectionUsd: number;
    }>;
    summary: {
      assumptions: { overheadMonthlyUsd: number; desktopShare: number; mobileShare: number };
    };
  }
  const { data: infraCosts } = useSWR<InfraCostsData>(
    token ? [`/api/omi/stats/infra-costs?days=${profitDays}`, token] : null,
    authFetcher,
    swrOpts,
  );

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

  // Cumulative Users chart fetches the full history since the first
  // signup so the growth curve is meaningful.
  const allDailyData = dailyNewUsers?.data ?? [];
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

  // Slice the all-time daily series to the selected window for the
  // Cumulative Users chart. Granularity stays daily; only the visible
  // range changes.
  const cumulativeSeries = useMemo(() => {
    if (allDailyData.length === 0) return allDailyData;
    if (cumulativeWindow === "all") return allDailyData;
    const days = cumulativeWindow === "7d" ? 7 : 30;
    return allDailyData.slice(-days);
  }, [allDailyData, cumulativeWindow]);

  // On a tight window the cumulative values barely move relative to the
  // absolute total, so pin the y-axis to the window's min/max. For the
  // full history we anchor at zero so the curve sweeps from 0 → total.
  const cumulativeYDomain: [number | "dataMin", number | "dataMax"] =
    cumulativeWindow === "all" ? [0, "dataMax"] : ["dataMin", "dataMax"];

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

  const profitCharts = useMemo<ChartItem[]>(() => {
    const summary = profitability?.summary;
    const usersData = profitability?.users ?? [];
    const revenueData = profitability?.revenue ?? [];
    const costData = profitability?.cost ?? [];
    const costPerUserData = (profitability as any)?.costPerUser ?? [];
    const conversionData = profitability?.conversion ?? [];
    const costSource = (summary?.assumptions as any)?.costSource as string | undefined;
    const avgCostDesktop = (summary as any)?.avgCostPerUserDesktop as number | undefined;
    const avgCostMobile = (summary as any)?.avgCostPerUserMobile as number | undefined;

    return [
      {
        id: "profit-users",
        title: "New users / day",
        subtitle: summary
          ? `Desktop ${summary.totalNewDesktop.toLocaleString()} · Mobile ${summary.totalNewMobile.toLocaleString()}`
          : "Per-platform signups",
        icon: <Users className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={usersData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} minTickGap={30} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={formatCompact} width={40} />
              <Tooltip contentStyle={tooltipStyle} labelFormatter={fullDate} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="desktop" stackId="u" fill="#6366f1" name="Desktop" />
              <Bar dataKey="mobile" stackId="u" fill="#22c55e" name="Mobile" />
            </BarChart>
          </ResponsiveContainer>
        ),
      },
      {
        id: "profit-revenue",
        title: "Revenue / day (est.)",
        subtitle: "Daily MRR share by platform active-user ratio",
        icon: <DollarSign className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={revenueData}>
              <defs>
                <linearGradient id="profitRevDesktop" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="profitRevMobile" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} minTickGap={30} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${formatCompact(v)}`} width={50} />
              <Tooltip contentStyle={tooltipStyle} labelFormatter={fullDate} formatter={(v: number, name) => [formatCurrency(v), name]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="desktop" stackId="r" stroke="#6366f1" strokeWidth={2} fill="url(#profitRevDesktop)" name="Desktop" />
              <Area type="monotone" dataKey="mobile" stackId="r" stroke="#22c55e" strokeWidth={2} fill="url(#profitRevMobile)" name="Mobile" />
            </AreaChart>
          </ResponsiveContainer>
        ),
      },
      {
        id: "profit-cost-per-user",
        title: `Cost / user / day${costSource === "real" ? "" : " (est.)"}`,
        subtitle: avgCostDesktop != null && avgCostMobile != null
          ? `Avg: Desktop $${avgCostDesktop.toFixed(2)} · Mobile $${avgCostMobile.toFixed(2)}`
          : "Daily infra spend ÷ active users, per platform",
        icon: <Activity className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={costPerUserData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} minTickGap={30} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${Number(v).toFixed(2)}`} width={56} />
              <Tooltip contentStyle={tooltipStyle} labelFormatter={fullDate} formatter={(v: number, name) => [`$${Number(v).toFixed(2)}`, name]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="desktop" stroke="#f59e0b" strokeWidth={2} dot={false} name="Desktop $/user" />
              <Line type="monotone" dataKey="mobile" stroke="#ef4444" strokeWidth={2} dot={false} name="Mobile $/user" />
            </LineChart>
          </ResponsiveContainer>
        ),
      },
      {
        id: "profit-cost",
        title: `Total infra cost / day${costSource === "real" ? "" : " (est.)"}`,
        subtitle: summary?.totalCostUsd != null
          ? `Total last ${profitability?.days ?? 30}d: ${formatCurrency(summary.totalCostUsd)}`
          : "Desktop + mobile daily burn",
        icon: <DollarSign className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={costData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} minTickGap={30} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${formatCompact(v)}`} width={50} />
              <Tooltip contentStyle={tooltipStyle} labelFormatter={fullDate} formatter={(v: number, name) => [formatCurrency(v), name]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="desktop" stackId="c" fill="#f59e0b" name="Desktop" />
              <Bar dataKey="mobile" stackId="c" fill="#ef4444" name="Mobile" />
            </BarChart>
          </ResponsiveContainer>
        ),
      },
      {
        id: "profit-conversion",
        title: "Free → paid %",
        subtitle: "New paid subs / new users",
        icon: <Percent className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={conversionData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} minTickGap={30} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `${v}%`} width={40} />
              <Tooltip contentStyle={tooltipStyle} labelFormatter={fullDate} formatter={(v: number, name) => [`${v}%`, name]} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="desktop" stroke="#6366f1" strokeWidth={2} dot={false} name="Desktop" />
              <Line type="monotone" dataKey="mobile" stroke="#22c55e" strokeWidth={2} dot={false} name="Mobile" />
            </LineChart>
          </ResponsiveContainer>
        ),
      },
      {
        id: "profit-cost-breakdown",
        title: "Infra cost by service — last 30 days",
        subtitle: infraCosts?.summary?.assumptions
          ? `Trailing-30-day actual spend, split by platform (Desktop ${Math.round((infraCosts.summary.assumptions.desktopShare ?? 0) * 100)}% · Mobile ${Math.round((infraCosts.summary.assumptions.mobileShare ?? 0) * 100)}%)`
          : "Per-service actual spend from GCP bill + external LLMs, split by platform",
        icon: <DollarSign className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 6 },
        render: () => {
          const rows = infraCosts?.breakdown ?? [];
          if (!rows.length) {
            return (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Loading cost breakdown…
              </div>
            );
          }
          const totalMtd = rows.reduce((s, r) => s + r.mtdUsd, 0);
          const totalProj = rows.reduce((s, r) => s + r.aprProjectionUsd, 0);
          const totalDesktopProj = rows.reduce((s, r) => s + r.desktopProjectionUsd, 0);
          const totalMobileProj = rows.reduce((s, r) => s + r.mobileProjectionUsd, 0);
          return (
            <div className="h-full overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-card">
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="px-3 py-2 text-left font-medium">Service</th>
                    <th className="px-3 py-2 text-right font-medium">Gross MTD</th>
                    <th className="px-3 py-2 text-right font-medium">Last 30 days</th>
                    <th className="px-3 py-2 text-right font-medium text-indigo-500">Desktop</th>
                    <th className="px-3 py-2 text-right font-medium text-green-500">Mobile</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.service} className="border-b border-border/40 last:border-b-0">
                      <td className="px-3 py-2 font-medium">{r.service}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(r.mtdUsd)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(r.aprProjectionUsd)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-indigo-500">{formatCurrency(r.desktopProjectionUsd)}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-red-500">{formatCurrency(r.mobileProjectionUsd)}</td>
                    </tr>
                  ))}
                  <tr className="border-t-2 border-border/60 font-semibold">
                    <td className="px-3 py-2">Total</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totalMtd)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{formatCurrency(totalProj)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-indigo-500">{formatCurrency(totalDesktopProj)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-red-500">{formatCurrency(totalMobileProj)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          );
        },
      },
    ];
  }, [profitability, infraCosts]);

  const revenueCharts = useMemo<ChartItem[]>(() => {
    return [
      {
        id: "rev-cumulative",
        title: "Cumulative users",
        subtitle: "Total users across all platforms",
        icon: <Users className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          cumulativeSeries.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={cumulativeSeries}>
                <defs>
                  <linearGradient id="cumulativeGradientRev" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={shortDate} minTickGap={40} />
                <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={formatCompact} domain={cumulativeYDomain} allowDataOverflow={false} width={56} />
                <Tooltip formatter={(value: number) => [value.toLocaleString(), "Total Users"]} labelFormatter={fullDate} contentStyle={tooltipStyle} />
                <Area type="monotone" dataKey="cumulative" stroke="#22c55e" strokeWidth={2} fill="url(#cumulativeGradientRev)" dot={false} activeDot={{ r: 4 }} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground text-sm">No data available</div>
          )
        ),
      },
      {
        id: "rev-mrr",
        title: "MRR over time",
        subtitle: "Monthly recurring revenue from Stripe",
        icon: <DollarSign className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={mrrData}>
              <defs>
                <linearGradient id="mrrGradientRev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLORS.area} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={COLORS.area} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="month" className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} tickFormatter={(v) => `$${formatCompact(v)}`} />
              <Tooltip formatter={(value: number) => [formatCurrency(value), "MRR"]} contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="mrr" stroke={COLORS.mrr} strokeWidth={2} fill="url(#mrrGradientRev)" dot={{ r: 3, fill: COLORS.mrr }} activeDot={{ r: 5 }} />
            </AreaChart>
          </ResponsiveContainer>
        ),
      },
      {
        id: "rev-subs",
        title: "New subscriptions",
        subtitle: "Monthly vs annual subscriptions created each month",
        icon: <TrendingUp className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
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
        ),
      },
    ];
  }, [cumulativeSeries, cumulativeYDomain, mrrData, subData]);

  const macosGrowthCharts = useMemo<ChartItem[]>(() => {
    return [
      {
        id: "macos-active-versions",
        title: "macOS Active Versions",
        subtitle: `Active users for ${macosVersionStats?.date ?? "today"}, split by release channel and app version`,
        icon: <Monitor className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 8 },
        render: () => (
          <div className="flex h-full flex-col">
            <div className="mb-3 flex items-center justify-end">
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
          </div>
        ),
      },
      {
        id: "macos-fb-sessions-per-user",
        title: "Floating Bar Sessions per User",
        subtitle: "Times floating bar was opened and a question asked, per user per day (follow-ups don't count)",
        icon: <Activity className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          <div className="flex h-full flex-col">
            {fbSummary && (
              <div className="mb-2 text-right text-sm text-muted-foreground">
                Avg: <span className="font-medium text-foreground">{fbSummary.overallAvgPerUserPerDay ?? "—"}</span> sessions/user/day
              </div>
            )}
            <div className="min-h-0 flex-1">
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
          </div>
        ),
      },
    ];
  }, [macosVersionStats, macosVersionStatsLoading, macosChannelData, macosVersionData, fbSummary, fbUsageLoading, fbUsageData]);

  const notificationCharts = useMemo<ChartItem[]>(() => {
    return [
      {
        id: "notif-daily-sent",
        title: "Daily Notifications Sent",
        initialLayout: { cols: 12, rows: 4 },
        icon: <Send className="h-4 w-4" />,
        render: () => (
          notificationStatsLoading ? (
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
          )
        ),
      },
      {
        id: "notif-hourly-168h",
        title: "Notifications Sent, Last 168 Hours",
        subtitle: "Hourly volume, with dates marked at midnight UTC.",
        icon: <Send className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          notificationStatsLoading ? (
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
          )
        ),
      },
      {
        id: "notif-fb-ctr",
        title: "Floating Bar Notification CTR",
        subtitle: floatingBarCtrSummary?.mode === "surface_tagged"
          ? "Sent vs clicked proactive notifications in the desktop floating bar."
          : "Surface-tagged floating-bar events are not populated yet, so this is currently using all desktop notification clicks as a fallback.",
        icon: <MousePointerClick className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          notificationStatsLoading ? (
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
          )
        ),
      },
      {
        id: "notif-weekly-reach",
        title: "Weekly Notification Reach",
        subtitle: "Volume and unique recipients in one view.",
        icon: <Users className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          notificationStatsLoading ? (
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
          )
        ),
      },
      {
        id: "notif-settings",
        title: "Notification Settings",
        subtitle: "Based on the desktop notifications_enabled toggle. Missing values default to enabled.",
        icon: <Bell className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
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
        ),
      },
    ];
  }, [
    notificationStatsLoading,
    notificationDailyCombined,
    notificationHourlyData,
    floatingBarCtr,
    floatingBarCtrSummary,
    notificationWeeklyCombined,
    notificationEnabledDisabled,
  ]);

  const ratingsAndUsageCharts = useMemo<ChartItem[]>(() => {
    return [
      {
        id: "ratings-weekly",
        title: "Chat Response Ratings",
        subtitle: "Weekly thumbs up/down from macOS floating bar. The overall positive rate is shown above.",
        icon: <MessageSquare className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          <div className="flex h-full flex-col">
            <div className="mb-2 flex items-center justify-end gap-4 text-sm text-muted-foreground">
              <span className="text-green-500 font-medium">{totalThumbsUp} up</span>
              <span className="text-red-500 font-medium">{totalThumbsDown} down</span>
              <span>{overallRatio}% positive</span>
            </div>
            <div className="min-h-0 flex-1">
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
          </div>
        ),
      },
      {
        id: "fb-usage-text-voice",
        title: "Floating Bar Usage",
        subtitle: "Daily queries by input type — text vs voice (last 30 days)",
        icon: <Activity className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          <div className="flex h-full flex-col">
            {fbSummary && (
              <div className="mb-2 flex items-center justify-end gap-4 text-sm text-muted-foreground">
                <span>{fbSummary.totalQueries} total</span>
                <span className="text-blue-500 font-medium">{fbSummary.totalText} text</span>
                <span className="text-orange-500 font-medium">{fbSummary.totalVoice} voice</span>
              </div>
            )}
            <div className="min-h-0 flex-1">
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
          </div>
        ),
      },
      {
        id: "fb-avg-per-user",
        title: "Avg Queries per User per Day",
        subtitle: "Average floating bar queries per active user, daily (last 30 days)",
        icon: <Activity className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          <div className="flex h-full flex-col">
            {fbSummary && (
              <div className="mb-2 text-right text-sm text-muted-foreground">
                Overall: <span className="font-medium text-foreground">{fbSummary.overallAvgPerUserPerDay}</span> queries/user/day
              </div>
            )}
            <div className="min-h-0 flex-1">
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
          </div>
        ),
      },
    ];
  }, [ratingsLoading, weeklyRatingsData, totalThumbsUp, totalThumbsDown, overallRatio, fbSummary, fbUsageLoading, fbUsageData]);

  const viralCharts = useMemo<ChartItem[]>(() => {
    return [
      {
        id: "viral-growth-accounting",
        title: "Growth Accounting",
        subtitle: "Weekly breakdown: where do active users come from? (Churned shown as negative)",
        icon: <TrendingUp className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          viralLoading ? (
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
          )
        ),
      },
      {
        id: "viral-dau",
        title: "Daily Active Users",
        subtitle: "Unique macOS users per day",
        icon: <Activity className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          dauLoading ? (
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
          )
        ),
      },
      {
        id: "viral-crash-rate",
        title: "App Stability",
        subtitle: "Daily crashes vs active users (last 30 days)",
        icon: <AlertTriangle className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => {
          const summaryLine = (() => {
            if (!crashRate?.data) return null;
            const recent = crashRate.data.slice(-7);
            const totalCrashes = recent.reduce((s, d) => s + d.crashes, 0);
            const totalUsers = recent.reduce((s, d) => s + d.users, 0);
            const rate = totalUsers > 0 ? ((1 - totalCrashes / totalUsers) * 100).toFixed(1) : "100.0";
            return `${rate}% crash-free (7d) · ${totalCrashes} crashes`;
          })();
          return (
            <div className="flex h-full flex-col">
              {summaryLine && (
                <div className="mb-2 text-right text-sm text-muted-foreground">{summaryLine}</div>
              )}
              <div className="min-h-0 flex-1">
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
            </div>
          );
        },
      },
      {
        id: "viral-daily-new-users",
        title: "Daily New Users",
        subtitle: "First-time sign-ins with 7-day rolling average",
        icon: <Users className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          <div className="flex h-full flex-col">
            {dailyWithRollingAvg.length > 0 && (
              <div className="mb-2 text-right text-sm text-muted-foreground">
                {dailyWithRollingAvg.reduce((s, p) => s + p.users, 0).toLocaleString()} in last 30d
              </div>
            )}
            <div className="min-h-0 flex-1">
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
          </div>
        ),
      },
      {
        id: "viral-stickiness",
        title: "Stickiness (DAU/WAU)",
        subtitle: "How often weekly users come back daily (good: 30%+)",
        icon: <Zap className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          viralLoading ? (
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
          )
        ),
      },
      {
        id: "viral-power-curve",
        title: "Power User Curve",
        subtitle: "Days active per user in last 30 days (right-skew = healthy)",
        icon: <Zap className="h-4 w-4" />,
        initialLayout: { cols: 6, rows: 4 },
        render: () => (
          viralLoading ? (
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
          )
        ),
      },
      {
        id: "viral-activation",
        title: "Activation Rate",
        subtitle: "% of new users who create a Memory within 7 days of signing up",
        icon: <Target className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          viralLoading ? (
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
          )
        ),
      },
    ];
  }, [viralLoading, ga, dauLoading, dauData, crashRate, crashRateLoading, dailyWithRollingAvg, dailyNewUsersLoading, stickinessData, powerCurve, activationData]);

  const retentionCharts = useMemo<ChartItem[]>(() => {
    if (retentionView !== "average") return [];
    return [
      {
        id: "retention-avg-curve",
        title: "Average Retention Curve",
        subtitle: mixpanelRetention?.totalUsers != null
          ? `${mixpanelRetention.totalCohorts} cohorts · ${mixpanelRetention.totalUsers.toLocaleString()} users`
          : "Weighted average retention across all cohorts",
        icon: <TrendingUp className="h-4 w-4" />,
        initialLayout: { cols: 12, rows: 4 },
        render: () => (
          mixpanelRetention?.data && mixpanelRetention.data.length > 0 ? (
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
          )
        ),
      },
    ];
  }, [retentionView, mixpanelRetention]);

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

      {/* Profitability by Platform — draggable & resizable */}
      <div className="pt-2">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">Profitability by Platform</h2>
            <p className="text-sm text-muted-foreground">
              Daily users, revenue, cost and free→paid conversion — desktop (macOS) vs mobile (iOS/Android). Revenue and
              cost per platform are estimates. Drag cards to reorder; drag the bottom-right corner to resize.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex overflow-hidden rounded-md border border-input">
              {([30, 60, 90] as const).map((d) => (
                <button
                  key={d}
                  onClick={() => setProfitDays(d)}
                  className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                    profitDays === d
                      ? "bg-primary text-primary-foreground"
                      : "bg-background text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
            <label className="flex items-center gap-1 text-xs text-muted-foreground">
              Desktop $/user/day
              <input
                type="number"
                step="0.01"
                min="0"
                value={desktopCostInput}
                onChange={(e) => setDesktopCostInput(e.target.value)}
                className="w-16 rounded-md border border-input bg-background px-2 py-1 text-xs"
              />
            </label>
            <label className="flex items-center gap-1 text-xs text-muted-foreground">
              Mobile $/user/day
              <input
                type="number"
                step="0.01"
                min="0"
                value={mobileCostInput}
                onChange={(e) => setMobileCostInput(e.target.value)}
                className="w-16 rounded-md border border-input bg-background px-2 py-1 text-xs"
              />
            </label>
          </div>
        </div>

        {profitError ? (
          <Card className="border-destructive/50 bg-destructive/5 p-4">
            <p className="text-sm text-destructive">Failed to load profitability data.</p>
          </Card>
        ) : profitLoading && !profitability ? (
          <Card className="flex h-[200px] items-center justify-center p-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </Card>
        ) : (
          <>
            {profitability?.summary.partial && (
              <div className="mb-3 flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>Some profitability inputs failed. Numbers may be incomplete.</span>
              </div>
            )}
            <ResizableChartGrid storageKey="admin:profitability:v1" items={profitCharts} />
          </>
        )}
      </div>

      {/* Revenue Overview — draggable & resizable */}
      <div className="pt-2">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-bold tracking-tight">Revenue Overview</h2>
          <div className="flex rounded-md border border-input overflow-hidden">
            {(["7d", "30d", "all"] as const).map((w) => (
              <button
                key={w}
                onClick={() => setCumulativeWindow(w)}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                  cumulativeWindow === w
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:bg-accent"
                }`}
              >
                {w === "7d" ? "Last week" : w === "30d" ? "Last month" : "All time"}
              </button>
            ))}
          </div>
        </div>
        {dailyNewUsersLoading ? (
          <Card className="flex h-[200px] items-center justify-center p-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </Card>
        ) : (
          <ResizableChartGrid storageKey="admin:revenue-overview:v1" items={revenueCharts} />
        )}
      </div>

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

      <ResizableChartGrid storageKey="admin:macos-growth:v1" items={macosGrowthCharts} />

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

      <ResizableChartGrid storageKey="admin:notifications:v1" items={notificationCharts} />

      {/* Ratings + Floating Bar Usage — draggable & resizable */}
      <ResizableChartGrid storageKey="admin:ratings-usage:v1" items={ratingsAndUsageCharts} />

      {/* Viral metrics — draggable & resizable */}
      <ResizableChartGrid storageKey="admin:viral-metrics:v1" items={viralCharts} />

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
        <ResizableChartGrid storageKey="admin:retention-avg:v1" items={retentionCharts} />
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

  const items = useMemo<ChartItem[]>(() => [
    {
      id: "chat-ratings",
      title: "Chat Response Ratings",
      subtitle:
        stats.total > 0
          ? `${stats.up} 👍 · ${stats.down} 👎 · ${stats.pct}% positive`
          : undefined,
      initialLayout: { cols: 12, rows: 5 },
      render: () => (
        <div className="flex h-full flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
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
                <button
                  key={g}
                  onClick={() => setGroupBy(g)}
                  className={`px-3 py-1 transition-colors ${
                    groupBy === g
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {g === "week" ? "By Week" : "By Version"}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1">
            {isLoading ? (
              <div className="flex h-full items-center justify-center text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading ratings...
              </div>
            ) : !chartData.length ? (
              <div className="flex h-full items-center justify-center text-center text-muted-foreground py-8">
                {groupBy === "version"
                  ? "No version-tagged ratings yet."
                  : "No chat ratings data available"}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
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
          </div>
        </div>
      ),
    },
  ], [platform, groupBy, isLoading, chartData, stats]);

  return <ResizableChartGrid storageKey="admin:chat-ratings:v1" items={items} />;
}
