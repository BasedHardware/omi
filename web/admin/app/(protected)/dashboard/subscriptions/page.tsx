'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from "@/components/ui/table";
import { 
  Search, 
  Filter, 
  Download, 
  RefreshCw,
  CreditCard,
  DollarSign,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  Users,
  AlertTriangle
} from "lucide-react";
import { useAuth } from "@/components/auth-provider";
import { useAuthFetch } from "@/hooks/useAuthToken";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Line, LineChart, XAxis, YAxis, CartesianGrid, Legend } from "recharts";

interface Subscription {
  id: string;
  customer: {
    id: string;
    email: string;
    name?: string;
  };
  status: string;
  current_period_start: number;
  current_period_end: number;
  created: number;
  items: {
    data: Array<{
      id: string;
      price: {
        id: string;
        unit_amount: number;
        currency: string;
        recurring: {
          interval: string;
        };
      };
      quantity: number;
    }>;
  };
  metadata?: Record<string, string>;
}

interface SubscriptionsResponse {
  subscriptions: Subscription[];
  total: number;
  has_more: boolean;
  has_previous: boolean;
  next_page: string | null;
  previous_page: string | null;
}

interface RevenueMetrics {
  mrr: number;
  arr: number;
}

interface SubscriptionCounts {
  monthly: number;
  annual: number;
}

interface SubscriptionTrendData {
  month: string;
  monthKey: string;
  monthly: number;
  annual: number;
}

interface MRRTrendData {
  month: string;
  monthKey: string;
  mrr: number;
}

export default function SubscriptionsPage() {
  const { user } = useAuth();
  const { fetchWithAuth, token } = useAuthFetch();
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [revenueMetrics, setRevenueMetrics] = useState<RevenueMetrics | null>(null);
  const [subscriptionCounts, setSubscriptionCounts] = useState<SubscriptionCounts | null>(null);
  const [subscriptionTrends, setSubscriptionTrends] = useState<SubscriptionTrendData[]>([]);
  const [mrrTrends, setMrrTrends] = useState<MRRTrendData[]>([]);
  const [hasPartialData, setHasPartialData] = useState(false);
  const [metricsError, setMetricsError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [hasMore, setHasMore] = useState(false);
  const [hasPrevious, setHasPrevious] = useState(false);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [previousPage, setPreviousPage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setHasPartialData(false);
    setMetricsError(false);
    fetchSubscriptions();
    fetchRevenueMetrics();
    fetchTotalCount();
    fetchSubscriptionCounts();
    fetchSubscriptionTrends();
    fetchMrrTrends();
  }, [statusFilter, token]);

  const fetchSubscriptions = async (pageParams?: { starting_after?: string; ending_before?: string }) => {
    try {
      // Use tableLoading for pagination, full loading for initial load
      if (pageParams) {
        setTableLoading(true);
      } else {
        setLoading(true);
      }
      // Build query parameters
      const params = new URLSearchParams();
      if (pageParams?.starting_after) {
        params.append('starting_after', pageParams.starting_after);
      }
      if (pageParams?.ending_before) {
        params.append('ending_before', pageParams.ending_before);
      }
      if (statusFilter !== 'all') {
        params.append('status', statusFilter);
      }

      // Fetch subscriptions data
      const response = await fetchWithAuth(`/api/omi/subscriptions?${params.toString()}`);

      if (!response.ok) {
        throw new Error('Failed to fetch subscriptions');
      }

      const data: SubscriptionsResponse = await response.json();
      setSubscriptions(data.subscriptions || []);
      setHasMore(data.has_more || false);
      setHasPrevious(data.has_previous || false);
      setNextPage(data.next_page || null);
      setPreviousPage(data.previous_page || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
      setTableLoading(false);
    }
  };

  const fetchTotalCount = async () => {
    try {
      // Fetch total count separately with status filter
      const countParams = new URLSearchParams();
      countParams.append('count_only', 'true');
      if (statusFilter !== 'all') {
        countParams.append('status', statusFilter);
      }

      const countResponse = await fetchWithAuth(`/api/omi/subscriptions?${countParams.toString()}`);

      if (countResponse.ok) {
        const countData = await countResponse.json();
        setTotalCount(countData.total_count || 0);
      }
    } catch (err) {
      console.error('Error fetching total count:', err);
    }
  };

  const handleNextPage = () => {
    if (nextPage) {
      fetchSubscriptions({ starting_after: nextPage });
    }
  };

  const handlePreviousPage = () => {
    if (previousPage) {
      fetchSubscriptions({ ending_before: previousPage });
    }
  };

  const handleRefresh = () => {
    setHasPartialData(false);
    setMetricsError(false);
    fetchSubscriptions();
    fetchRevenueMetrics();
    fetchTotalCount();
    fetchSubscriptionCounts();
    fetchSubscriptionTrends();
    fetchMrrTrends();
  };

  const fetchRevenueMetrics = async () => {
    try {
      const response = await fetchWithAuth('/api/omi/stats/revenue');

      if (response.ok) {
        const data = await response.json();
        if (data.partial) setHasPartialData(true);
        setRevenueMetrics(data);
      } else {
        setRevenueMetrics(null);
        setMetricsError(true);
      }
    } catch (err) {
      console.error('Error fetching revenue metrics:', err);
      setRevenueMetrics(null);
      setMetricsError(true);
    }
  };

  const fetchSubscriptionCounts = async () => {
    try {
      const response = await fetchWithAuth('/api/omi/stats/subscriptions');

      if (response.ok) {
        const data = await response.json();
        if (data.partial) setHasPartialData(true);
        setSubscriptionCounts({
          monthly: data.priceIdOne?.count || 0,
          annual: data.priceIdTwo?.count || 0,
        });
      } else {
        setSubscriptionCounts(null);
        setMetricsError(true);
      }
    } catch (err) {
      console.error('Error fetching subscription counts:', err);
      setSubscriptionCounts(null);
      setMetricsError(true);
    }
  };

  const fetchSubscriptionTrends = async () => {
    try {
      const response = await fetchWithAuth('/api/omi/stats/subscription-trends?months=6');

      if (response.ok) {
        const data = await response.json();
        if (data.partial) setHasPartialData(true);
        setSubscriptionTrends(data.data || []);
      } else {
        setSubscriptionTrends([]);
        setMetricsError(true);
      }
    } catch (err) {
      console.error('Error fetching subscription trends:', err);
      setSubscriptionTrends([]);
      setMetricsError(true);
    }
  };

  const fetchMrrTrends = async () => {
    try {
      const response = await fetchWithAuth('/api/omi/stats/mrr-trends?months=6');

      if (response.ok) {
        const data = await response.json();
        if (data.partial) setHasPartialData(true);
        setMrrTrends(data.data || []);
      } else {
        setMrrTrends([]);
        setMetricsError(true);
      }
    } catch (err) {
      console.error('Error fetching MRR trends:', err);
      setMrrTrends([]);
      setMetricsError(true);
    }
  };

  const formatDate = (timestamp: number) => {
    return new Date(timestamp * 1000).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatCurrency = (amount: number, currency: string) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency.toUpperCase(),
    }).format(amount / 100);
  };

  const getStatusBadge = (status: string) => {
    const statusConfig = {
      active: { variant: 'default' as const, label: 'Active' },
      canceled: { variant: 'destructive' as const, label: 'Canceled' },
      past_due: { variant: 'secondary' as const, label: 'Past Due' },
      trialing: { variant: 'outline' as const, label: 'Trialing' },
      unpaid: { variant: 'destructive' as const, label: 'Unpaid' },
    };

    const config = statusConfig[status as keyof typeof statusConfig] || { 
      variant: 'outline' as const, 
      label: status 
    };

    return <Badge variant={config.variant}>{config.label}</Badge>;
  };

  const filteredSubscriptions = subscriptions.filter(subscription => {
    const matchesSearch = 
      subscription.customer.email.toLowerCase().includes(searchTerm.toLowerCase()) ||
      subscription.customer.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      subscription.id.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesStatus = statusFilter === 'all' || subscription.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="h-8 w-8 animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-10">
        <p className="text-destructive mb-4">{error}</p>
        <Button onClick={() => fetchSubscriptions()}>Retry</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {metricsError && (
        <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Some metrics failed to load. Displayed values may be unavailable or incomplete.</span>
        </div>
      )}
      {hasPartialData && !metricsError && (
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          <span>Some data sources failed to load. Numbers may be incomplete.</span>
        </div>
      )}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Subscriptions</h1>
          <p className="text-muted-foreground">
            Manage and monitor all subscription details
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
          <Button variant="outline">
            <Download className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>
      </div>

      {/* Revenue Metrics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">MRR</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {revenueMetrics ? `$${revenueMetrics.mrr.toLocaleString()}` : metricsError ? 'N/A' : '$0'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">ARR</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {revenueMetrics ? `$${revenueMetrics.arr.toLocaleString()}` : metricsError ? 'N/A' : '$0'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Monthly Subscriptions</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {subscriptionCounts ? subscriptionCounts.monthly.toLocaleString() : metricsError ? 'N/A' : '0'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active monthly subscriptions
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Annual Subscriptions</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {subscriptionCounts ? subscriptionCounts.annual.toLocaleString() : metricsError ? 'N/A' : '0'}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active annual subscriptions
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Subscription Creation Trends</CardTitle>
            <CardDescription>
              Monthly and annual subscriptions created over the last 6 months
            </CardDescription>
          </CardHeader>
          <CardContent>
            {subscriptionTrends.length > 0 ? (
              <ChartContainer
                config={{
                  monthly: {
                    label: "Monthly",
                    color: "hsl(var(--chart-1))",
                  },
                  annual: {
                    label: "Annual",
                    color: "hsl(var(--chart-2))",
                  },
                }}
                className="h-[300px] w-full"
              >
                <LineChart data={subscriptionTrends} margin={{ top: 5, right: 10, left: 0, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11 }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis tick={{ fontSize: 12 }} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="monthly"
                    stroke="hsl(var(--chart-1))"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    name="Monthly"
                  />
                  <Line
                    type="monotone"
                    dataKey="annual"
                    stroke="hsl(var(--chart-2))"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    name="Annual"
                  />
                </LineChart>
              </ChartContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                {metricsError ? 'Chart data unavailable' : 'Loading chart data...'}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Monthly Recurring Revenue (MRR)</CardTitle>
            <CardDescription>
              MRR trend over the last 6 months
            </CardDescription>
          </CardHeader>
          <CardContent>
            {mrrTrends.length > 0 ? (
              <ChartContainer
                config={{
                  mrr: {
                    label: "MRR",
                    color: "hsl(var(--chart-1))",
                  },
                }}
                className="h-[300px] w-full"
              >
                <LineChart data={mrrTrends} margin={{ top: 5, right: 10, left: 0, bottom: 40 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="month"
                    tick={{ fontSize: 11 }}
                    interval={0}
                    angle={-30}
                    textAnchor="end"
                    height={60}
                  />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    tickFormatter={(value) => `$${value.toLocaleString()}`}
                  />
                  <ChartTooltip
                    content={<ChartTooltipContent formatter={(value) => `$${Number(value).toLocaleString()}`} />}
                  />
                  <Line
                    type="monotone"
                    dataKey="mrr"
                    stroke="hsl(var(--chart-1))"
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    name="MRR"
                  />
                </LineChart>
              </ChartContainer>
            ) : (
              <div className="h-[300px] flex items-center justify-center text-muted-foreground">
                {metricsError ? 'Chart data unavailable' : 'Loading chart data...'}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>
            Search and filter subscriptions
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search by email, name, or subscription ID..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 border border-input rounded-md bg-background"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="canceled">Canceled</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Subscriptions Table */}
      <Card>
        <CardHeader>
          <CardTitle>All Subscriptions</CardTitle>
          <CardDescription>
            {filteredSubscriptions.length} subscription(s) found
          </CardDescription>
        </CardHeader>
        <CardContent>
          {tableLoading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Subscription ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredSubscriptions.map((subscription) => (
                  <TableRow key={subscription.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">
                          {subscription.customer.name || 'N/A'}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {subscription.customer.email}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {subscription.id}
                    </TableCell>
                    <TableCell>
                      {getStatusBadge(subscription.status)}
                    </TableCell>
                    <TableCell>
                      {subscription.items.data.map((item, index) => (
                        <div key={item.id} className="text-sm">
                          {item.quantity}x {item.price.recurring.interval}
                        </div>
                      ))}
                    </TableCell>
                    <TableCell>
                      {subscription.items.data.map((item, index) => (
                        <div key={item.id} className="text-sm">
                          {formatCurrency(item.price.unit_amount * item.quantity, item.price.currency)}
                        </div>
                      ))}
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDate(subscription.created)}
                    </TableCell>
                  </TableRow>
                ))}
                {filteredSubscriptions.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      No subscriptions found matching your criteria.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination Controls */}
      {(hasMore || hasPrevious) && (
        <Card>
          <CardContent className="flex items-center justify-between p-4">
            <div className="text-sm text-muted-foreground">
              Showing {subscriptions.length} subscriptions
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePreviousPage}
                disabled={!hasPrevious}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleNextPage}
                disabled={!hasMore}
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
