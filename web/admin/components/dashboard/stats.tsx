"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Package, Loader2, MessageSquare, CreditCard, Smartphone, AlertTriangle } from "lucide-react";
import useSWR from 'swr';
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";

interface AppStats {
  total: number;
  approved: number;
  inReview: number;
  paid: number;
  partial?: boolean;
}

interface SubscriptionStats {
  totalSubscriptions: number;
  partial?: boolean;
  priceIdOne: {
    count: number;
    priceId: string;
  };
  priceIdTwo: {
    count: number;
    priceId: string;
  };
}

interface AppSubscriptionStats {
  totalAppSubscriptions: number;
  uniqueCustomers: number;
  priceBreakdown: Record<string, number>;
  uniquePriceIds: number;
}

const PartialDataBadge = () => (
  <span className="inline-flex items-center gap-1 text-xs text-amber-600" title="Some data sources failed to load. Numbers may be incomplete.">
    <AlertTriangle className="h-3 w-3" />
    <span>Partial</span>
  </span>
);

const StatItem = ({ color, count, label }: { color: string; count: number; label: string }) => (
  <div className="flex items-center gap-2 text-sm text-muted-foreground">
    <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />
    <span>{count.toLocaleString()}</span>
    <span>{label}</span>
  </div>
);

export function DashboardStats() {
  const { token, loading: tokenLoading } = useAuthToken();

  // Fetch app stats using SWR with authentication
  const { 
    data: appStats,
    error: appStatsError,
    isLoading: appStatsLoading 
  } = useSWR<AppStats>(
    token ? ['/api/omi/apps/stats', token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  // Fetch conversation count using SWR
  const {
    data: conversationData,
    error: conversationError,
    isLoading: conversationLoading
  } = useSWR<{ totalConversations: number }>(
    token ? ['/api/omi/stats/conversation-count', token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  // Fetch subscription stats using SWR
  const {
    data: subscriptionData,
    error: subscriptionError,
    isLoading: subscriptionLoading
  } = useSWR<SubscriptionStats>(
    token ? ['/api/omi/stats/subscriptions', token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  // Fetch app subscription stats using SWR
  const {
    data: appSubscriptionData,
    error: appSubscriptionError,
    isLoading: appSubscriptionLoading
  } = useSWR<AppSubscriptionStats>(
    token ? ['/api/omi/stats/app-subscriptions', token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  // Helper to render a generic loading card
  const LoadingCard = ({ height = 'h-[180px]' }: { height?: string }) => (
    <Card className={height}>
      <CardContent className="p-6 flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </CardContent>
    </Card>
  );

  // Helper to render a generic error card
  const ErrorCard = ({ title, error, height = 'h-[180px]' }: { title: string, error: any, height?: string }) => {
    const errorMessage = error?.info?.message || error?.message || 'Could not load data.';
    return (
      <Card className={height}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-base font-medium text-muted-foreground">{title}</CardTitle>
          </CardHeader>
           <CardContent className="p-6 flex flex-col items-center justify-center h-full text-center grow">
              <p className="text-destructive text-sm mb-1">Error</p>
              <p className="text-xs text-muted-foreground">{errorMessage}</p>
          </CardContent>
      </Card>
    );
  };

  // Main render logic - Use grid layout
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {/* --- Apps Card --- */}
      {appStatsError ? (
        <ErrorCard title="Apps" error={appStatsError} />
      ) : tokenLoading || appStatsLoading ? (
        <LoadingCard />
      ) : appStats && appStats.total !== undefined ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div className="flex items-center gap-2">
              <CardTitle className="text-base font-medium text-muted-foreground">Apps</CardTitle>
              {appStats.partial && <PartialDataBadge />}
            </div>
            <Package className="h-5 w-5 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-3 pt-0 pb-6 px-6">
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold">{(appStats.total ?? 0).toLocaleString()}</p>
              <p className="text-sm text-muted-foreground">Total</p>
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <StatItem color="bg-green-500" count={appStats.approved ?? 0} label="Approved" />
              <StatItem color="bg-yellow-500" count={appStats.inReview ?? 0} label="In Review" />
              <StatItem color="bg-blue-500" count={appStats.paid ?? 0} label="Paid" />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="h-[180px]">
          <CardContent className="p-6 flex items-center justify-center h-full">
            <p className="text-muted-foreground">No app data available.</p>
          </CardContent>
        </Card>
      )}

      {/* --- Conversations Card --- */}
      {conversationError ? (
        <ErrorCard title="Conversations" error={conversationError} />
      ) : tokenLoading || conversationLoading ? (
        <LoadingCard />
      ) : conversationData && conversationData.totalConversations !== undefined ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-base font-medium text-muted-foreground">Conversations</CardTitle>
            <MessageSquare className="h-5 w-5 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-3 pt-0 pb-6 px-6">
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold">{(conversationData.totalConversations ?? 0).toLocaleString()}</p>
              <p className="text-sm text-muted-foreground">Total</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="h-[180px]">
          <CardContent className="p-6 flex items-center justify-center h-full">
            <p className="text-muted-foreground">Conversation data unavailable.</p>
          </CardContent>
        </Card>
      )}

      {/* --- Subscriptions Card --- */}
      {subscriptionError ? (
        <ErrorCard title="Active OMI Subscriptions" error={subscriptionError} />
      ) : tokenLoading || subscriptionLoading ? (
        <LoadingCard />
      ) : subscriptionData && subscriptionData.totalSubscriptions !== undefined ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div className="flex items-center gap-2">
              <CardTitle className="text-base font-medium text-muted-foreground">Active OMI Subscriptions</CardTitle>
              {subscriptionData.partial && <PartialDataBadge />}
            </div>
            <CreditCard className="h-5 w-5 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-3 pt-0 pb-6 px-6">
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold">{(subscriptionData.totalSubscriptions ?? 0).toLocaleString()}</p>
              <p className="text-sm text-muted-foreground">Total</p>
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <StatItem color="bg-purple-500" count={subscriptionData.priceIdOne?.count ?? 0} label="Monthly" />
              <StatItem color="bg-indigo-500" count={subscriptionData.priceIdTwo?.count ?? 0} label="Annual" />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="h-[180px]">
          <CardContent className="p-6 flex items-center justify-center h-full">
            <p className="text-muted-foreground">Subscription data unavailable.</p>
          </CardContent>
        </Card>
      )}

      {/* --- App Subscriptions Card --- */}
      {appSubscriptionError ? (
        <ErrorCard title="App Subscriptions" error={appSubscriptionError} />
      ) : tokenLoading || appSubscriptionLoading ? (
        <LoadingCard />
      ) : appSubscriptionData && appSubscriptionData.totalAppSubscriptions !== undefined ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-base font-medium text-muted-foreground">App Subscriptions</CardTitle>
            <Smartphone className="h-5 w-5 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-3 pt-0 pb-6 px-6">
            <div className="flex items-baseline gap-2">
              <p className="text-3xl font-bold">{(appSubscriptionData.totalAppSubscriptions ?? 0).toLocaleString()}</p>
              <p className="text-sm text-muted-foreground">Total</p>
            </div>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <StatItem color="bg-emerald-500" count={appSubscriptionData.uniqueCustomers ?? 0} label="Customers" />
              <StatItem color="bg-teal-500" count={appSubscriptionData.uniquePriceIds ?? 0} label="Price Plans" />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="h-[180px]">
          <CardContent className="p-6 flex items-center justify-center h-full">
            <p className="text-muted-foreground">App subscription data unavailable.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}