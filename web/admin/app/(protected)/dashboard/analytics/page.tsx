"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DollarSign,
  TrendingUp,
  Users,
  MessageSquare,
  Loader2,
} from "lucide-react";
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
  BarChart,
  LineChart,
  Area,
  AreaChart,
} from "recharts";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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
  data: { date: string; users: number }[];
  totalUsers: number;
  days: number;
}

interface OnboardingStepData {
  key: string;
  label: string;
  users: number;
  completionRate: number;
}

interface OnboardingData {
  days: number;
  totalUsers: number;
  methodology?: string;
  steps: OnboardingStepData[];
}

interface KFactorProxyData {
  newUsers: number;
  sharers: number;
  shareEvents: number;
  shareRatePct: number;
  sharesPerSharer: number;
  sharesPerNewUser: number;
}

interface KFactorData {
  days: number;
  available: boolean;
  kFactor: number | null;
  reason: string;
  proxy: KFactorProxyData;
}

const fetcher = (url: string) =>
  fetch(url).then((res) => {
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  });

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
  const d = new Date(`${dateStr}T00:00:00`);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function AnalyticsPage() {
  const [months, setMonths] = useState(12);
  const [retentionDays, setRetentionDays] = useState(15);
  const [retentionPlatform, setRetentionPlatform] = useState("macos");
  const [retentionView, setRetentionView] = useState<"average" | "cohorts">("average");
  const retentionIntervals = 10;
  const swrOptions = {
    revalidateOnFocus: false,
    revalidateOnReconnect: false,
    revalidateIfStale: false,
    shouldRetryOnError: false,
    errorRetryCount: 0,
    refreshInterval: 0,
  };

  const { data: revenue, isLoading: revenueLoading } = useSWR<RevenueData>(
    "/api/omi/stats/revenue",
    fetcher,
    swrOptions
  );

  const { data: mrrTrends, isLoading: mrrLoading } = useSWR<{
    data: MrrTrendPoint[];
  }>(`/api/omi/stats/mrr-trends?months=${months}`, fetcher, swrOptions);

  const { data: subTrends, isLoading: subTrendsLoading } = useSWR<{
    data: SubscriptionTrendPoint[];
  }>(`/api/omi/stats/subscription-trends?months=${months}`, fetcher, swrOptions);

  const { data: subCounts, isLoading: subCountsLoading } = useSWR<SubscriptionCounts>(
    "/api/omi/stats/subscriptions",
    fetcher,
    swrOptions
  );

  const { data: convCount, isLoading: convLoading } = useSWR<ConversationCount>(
    "/api/omi/stats/conversation-count",
    fetcher,
    swrOptions
  );

  const { data: dailyNewUsers, isLoading: dailyNewUsersLoading } = useSWR<DailyNewUsersData>(
    "/api/omi/stats/daily-new-users?days=30",
    fetcher,
    swrOptions
  );

  const retentionPlatformParam = retentionPlatform ? `&platform=${retentionPlatform}` : "";

  const { data: onboardingData, isLoading: onboardingLoading } = useSWR<OnboardingData>(
    `/api/omi/stats/onboarding/posthog?days=${retentionDays}`,
    fetcher,
    swrOptions
  );

  const { data: retentionData, isLoading: retentionLoading } = useSWR<RetentionData>(
    `/api/omi/stats/retention/posthog?days=${retentionDays}&intervals=${retentionIntervals}${retentionPlatformParam}`,
    fetcher,
    swrOptions
  );

  const { data: kFactorData, isLoading: kFactorLoading } = useSWR<KFactorData>(
    `/api/omi/stats/k-factor/posthog?days=${retentionDays}`,
    fetcher,
    swrOptions
  );

  const isLoading =
    revenueLoading ||
    mrrLoading ||
    subTrendsLoading ||
    subCountsLoading ||
    convLoading;

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const mrr = revenue?.mrr ?? 0;
  const arr = revenue?.arr ?? 0;
  const totalSubs = subCounts?.totalSubscriptions ?? 0;
  const monthlySubs = subCounts?.priceIdOne?.count ?? 0;
  const annualSubs = subCounts?.priceIdTwo?.count ?? 0;
  const totalConversations = convCount?.totalConversations ?? 0;
  const mrrData = mrrTrends?.data ?? [];
  const subData = subTrends?.data ?? [];
  const dailyData = dailyNewUsers?.data ?? [];
  const onboardingSteps = onboardingData?.steps ?? [];
  const cohorts = retentionData?.cohorts ?? [];
  const kFactorProxy = kFactorData?.proxy;

  let mrrGrowthPct: number | null = null;
  if (mrrData.length >= 2) {
    const current = mrrData[mrrData.length - 1].mrr;
    const previous = mrrData[mrrData.length - 2].mrr;
    if (previous > 0) {
      mrrGrowthPct = ((current - previous) / previous) * 100;
    }
  }

  let cohortMaxDays = 0;
  for (const cohort of cohorts) {
    if (cohort.data.length > cohortMaxDays) {
      cohortMaxDays = cohort.data.length;
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Analytics Dashboard</h1>
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

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Monthly Recurring Revenue
            </CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(mrr)}</div>
            {mrrGrowthPct !== null && (
              <p className={`text-xs ${mrrGrowthPct >= 0 ? "text-green-600" : "text-red-600"}`}>
                {mrrGrowthPct >= 0 ? "+" : ""}
                {mrrGrowthPct.toFixed(1)}% from last month
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Annual Run Rate
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(arr)}</div>
            <p className="text-xs text-muted-foreground">Based on current MRR</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Active Subscriptions
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalSubs.toLocaleString()}</div>
            <p className="text-xs text-muted-foreground">
              {monthlySubs.toLocaleString()} monthly &middot; {annualSubs.toLocaleString()} annual
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Conversations
            </CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCompact(totalConversations)}</div>
            <p className="text-xs text-muted-foreground">All time (Typesense)</p>
          </CardContent>
        </Card>
      </div>

      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">MRR Over Time</h2>
        <p className="text-sm text-muted-foreground mb-4">
          Monthly recurring revenue from Stripe (monthly + annualized)
        </p>
        <div className="h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={mrrData}>
              <defs>
                <linearGradient id="mrrGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={COLORS.area} stopOpacity={0.2} />
                  <stop offset="95%" stopColor={COLORS.area} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="month"
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
                tickFormatter={(v) => `$${formatCompact(v)}`}
              />
              <Tooltip
                formatter={(value: number) => [formatCurrency(value), "MRR"]}
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                }}
              />
              <Area
                type="monotone"
                dataKey="mrr"
                stroke={COLORS.mrr}
                strokeWidth={2}
                fill="url(#mrrGradient)"
                dot={{ r: 3, fill: COLORS.mrr }}
                activeDot={{ r: 5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="p-6">
        <h2 className="text-lg font-semibold mb-1">New Subscriptions</h2>
        <p className="text-sm text-muted-foreground mb-4">
          New monthly vs annual subscriptions created each month
        </p>
        <div className="h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={subData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="month"
                className="text-xs"
                tick={{ fill: "hsl(var(--muted-foreground))" }}
              />
              <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                }}
              />
              <Legend />
              <Bar
                dataKey="monthly"
                name="Monthly Plan"
                fill={COLORS.monthly}
                radius={[2, 2, 0, 0]}
                stackId="a"
              />
              <Bar
                dataKey="annual"
                name="Annual Plan"
                fill={COLORS.annual}
                radius={[2, 2, 0, 0]}
                stackId="a"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold">Daily New Users</h2>
          {dailyNewUsers?.totalUsers != null && (
            <span className="text-sm text-muted-foreground">
              {dailyNewUsers.totalUsers.toLocaleString()} total in last {dailyNewUsers.days} days
            </span>
          )}
        </div>
        <p className="text-sm text-muted-foreground mb-4">New user signups per day from Firebase</p>
        <div className="h-[400px]">
          {dailyNewUsersLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : dailyData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis
                  dataKey="date"
                  className="text-xs"
                  tick={{ fill: "hsl(var(--muted-foreground))" }}
                  tickFormatter={(v) => {
                    const d = new Date(`${v}T00:00:00`);
                    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
                  }}
                />
                <YAxis className="text-xs" tick={{ fill: "hsl(var(--muted-foreground))" }} />
                <Tooltip
                  formatter={(value: number) => [value.toLocaleString(), "New Users"]}
                  labelFormatter={(label) => {
                    const d = new Date(`${label}T00:00:00`);
                    return d.toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    });
                  }}
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                  }}
                />
                <Bar
                  dataKey="users"
                  name="New Users"
                  fill="#6366f1"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No data available
            </div>
          )}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[2fr,1fr]">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">Onboarding Completion Funnel</h2>
            {onboardingData?.totalUsers != null && (
              <span className="text-sm text-muted-foreground">
                {onboardingData.totalUsers.toLocaleString()} first-time entrants
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Sequential macOS onboarding completion rate for users whose first recorded current-flow
            onboarding event was `Name` in the last {retentionDays} days
          </p>
          {onboardingData?.methodology && (
            <p className="text-xs text-muted-foreground mb-4">{onboardingData.methodology}</p>
          )}
          <div className="h-[360px]">
            {onboardingLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : onboardingSteps.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={onboardingSteps} margin={{ left: 8, right: 24, top: 12, bottom: 70 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="label"
                    angle={-35}
                    textAnchor="end"
                    interval={0}
                    height={80}
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                  />
                  <YAxis
                    domain={[0, 100]}
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                    tickFormatter={(v) => `${v}%`}
                  />
                  <Tooltip
                    formatter={(value: number, name) =>
                      name === "completionRate"
                        ? [`${value}%`, "Completion"]
                        : [formatCompact(value), "Users"]
                    }
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="completionRate"
                    stroke="#0f766e"
                    strokeWidth={3}
                    dot={{ r: 3, fill: "#0f766e" }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                No onboarding data available
              </div>
            )}
          </div>
        </Card>

        <Card className="p-6">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">K-Factor</h2>
            <span className="text-sm text-muted-foreground">macOS only</span>
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Viral growth requires invite and accepted referral tracking
          </p>
          {kFactorLoading ? (
            <div className="flex items-center justify-center h-[280px]">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-lg border bg-muted/30 p-4">
                <div className="text-sm font-medium">Current Status</div>
                <div className="mt-1 text-2xl font-semibold">
                  {kFactorData?.available ? `${kFactorData.kFactor?.toFixed(2)}%` : "Unavailable"}
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{kFactorData?.reason}</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg border p-3">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    Share Rate
                  </div>
                  <div className="mt-1 text-xl font-semibold">
                    {kFactorProxy ? `${kFactorProxy.shareRatePct.toFixed(1)}%` : "0%"}
                  </div>
                  <div className="text-xs text-muted-foreground">Sharers / new users</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    Share Events
                  </div>
                  <div className="mt-1 text-xl font-semibold">
                    {kFactorProxy ? formatCompact(kFactorProxy.shareEvents) : "0"}
                  </div>
                  <div className="text-xs text-muted-foreground">Last {retentionDays} days</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs uppercase tracking-wide text-muted-foreground">
                    Shares / Sharer
                  </div>
                  <div className="mt-1 text-xl font-semibold">
                    {kFactorProxy ? kFactorProxy.sharesPerSharer.toFixed(2) : "0.00"}
                  </div>
                  <div className="text-xs text-muted-foreground">Proxy only</div>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Retention by Cohort</h2>
          <p className="text-sm text-muted-foreground">
            PostHog-backed macOS retention from the `App Became Active` event
          </p>
          <p className="text-xs text-muted-foreground">
            Matching PostHog daily cohorts with simple mean and {retentionIntervals}-day return window
          </p>
        </div>
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
            <SelectTrigger className="w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="macos">macOS</SelectItem>
              <SelectItem value="all">All Platforms</SelectItem>
            </SelectContent>
          </Select>
          <Select value={String(retentionDays)} onValueChange={(v) => setRetentionDays(parseInt(v, 10))}>
            <SelectTrigger className="w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="14">14 days</SelectItem>
              <SelectItem value="15">15 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="60">60 days</SelectItem>
              <SelectItem value="90">90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {retentionLoading ? (
        <Card className="p-6">
          <div className="flex items-center justify-center h-[400px]">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </Card>
      ) : retentionView === "average" ? (
        <Card className="p-6">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-lg font-semibold">Average Retention</h2>
            {retentionData?.totalUsers != null && (
              <span className="text-sm text-muted-foreground">
                {retentionData.totalCohorts} cohorts &middot;{" "}
                {retentionData.totalUsers.toLocaleString()} users
              </span>
            )}
          </div>
          <p className="text-sm text-muted-foreground mb-4">
            Simple mean daily retention across visible cohorts
          </p>
          <div className="h-[400px]">
            {retentionData?.data && retentionData.data.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={retentionData.data}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="day"
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                    tickFormatter={(v) => `D${v}`}
                  />
                  <YAxis
                    className="text-xs"
                    tick={{ fill: "hsl(var(--muted-foreground))" }}
                    tickFormatter={(v) => `${v}%`}
                    domain={[0, 100]}
                  />
                  <Tooltip
                    formatter={(value: number) => [`${value}%`, "Retention"]}
                    labelFormatter={(label) => `Day ${label}`}
                    contentStyle={{
                      backgroundColor: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="retention"
                    stroke="#f97316"
                    strokeWidth={2}
                    dot={{ r: 2, fill: "#f97316" }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-muted-foreground">
                No retention data available
              </div>
            )}
          </div>
        </Card>
      ) : (
        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b">
                  <th className="sticky left-0 z-10 bg-card px-4 py-3 text-left font-medium text-muted-foreground whitespace-nowrap">
                    Date
                  </th>
                  <th className="px-3 py-3 text-right font-medium text-muted-foreground whitespace-nowrap">
                    Users
                  </th>
                  {Array.from({ length: cohortMaxDays }, (_, i) => (
                    <th
                      key={i}
                      className="px-3 py-3 text-center font-medium text-muted-foreground whitespace-nowrap min-w-[64px]"
                    >
                      {i === 0 ? "< 1 Day" : `Day ${i}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {retentionData?.data && retentionData.data.length > 0 && (
                  <tr className="border-b font-semibold">
                    <td className="sticky left-0 z-10 bg-card px-4 py-2.5 whitespace-nowrap">
                      Weighted Avg
                    </td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">
                      {retentionData.totalUsers.toLocaleString()}
                    </td>
                    {retentionData.data.map((point) => (
                      <td
                        key={point.day}
                        className="px-3 py-2.5 text-center"
                        style={{ backgroundColor: retentionHeatColor(point.retention) }}
                      >
                        <span className={point.retention > 50 ? "text-white" : ""}>
                          {point.retention.toFixed(1)}%
                        </span>
                      </td>
                    ))}
                  </tr>
                )}
                {cohorts.map((cohort) => (
                  <tr key={cohort.date} className="border-b last:border-b-0 hover:bg-muted/30">
                    <td className="sticky left-0 z-10 bg-card px-4 py-2 whitespace-nowrap">
                      {formatCohortDate(cohort.date)}
                    </td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{cohort.users}</td>
                    {Array.from({ length: cohortMaxDays }, (_, i) => {
                      const val = i < cohort.data.length ? cohort.data[i].retention : null;
                      return (
                        <td
                          key={i}
                          className="px-3 py-2 text-center"
                          style={val !== null ? { backgroundColor: retentionHeatColor(val) } : {}}
                        >
                          {val !== null ? (
                            <span className={val > 50 ? "text-white" : ""}>
                              {val.toFixed(1)}%
                            </span>
                          ) : null}
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
