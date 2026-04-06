'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useAllPayouts } from '@/hooks/useAllPayouts';
import { useAuth } from '@/components/auth-provider';
import { PayoutWithAppInfo } from '@/lib/services/omi-api/types';
import { formatCurrency, formatDate } from '@/lib/utils';
import { DollarSign, RefreshCw, Filter } from 'lucide-react';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from "@/components/ui/select";

function PayoutStatusBadge({ status }: { status: string }) {
  const statusConfig = {
    paid: { variant: 'default' as const, label: 'Paid' },
    pending: { variant: 'secondary' as const, label: 'Pending' },
    in_transit: { variant: 'outline' as const, label: 'In Transit' },
    canceled: { variant: 'destructive' as const, label: 'Canceled' },
    failed: { variant: 'destructive' as const, label: 'Failed' },
  };

  const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.pending;

  return <Badge variant={config.variant}>{config.label}</Badge>;
}

function PayoutCard({ payoutData }: { payoutData: PayoutWithAppInfo }) {
  const { payout, appName, uid } = payoutData;

  return (
    <Card className="mb-4 hover:shadow-md transition-shadow">
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="font-semibold text-lg">
              {formatCurrency(payout.amount / 100, payout.currency)}
            </h3>
            <p className="text-sm text-muted-foreground">
              Payout ID: {payout.id}
            </p>
          </div>
          <PayoutStatusBadge status={payout.status} />
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm mb-4">
          <div>
            <span className="text-muted-foreground">App:</span>
            <p className="font-medium">{appName}</p>
          </div>
          <div>
            <span className="text-muted-foreground">User ID:</span>
            <p className="font-medium">{uid}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Created:</span>
            <p>{formatDate(payout.created * 1000)}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
          <div>
            <span className="text-muted-foreground">Method:</span>
            <p className="capitalize">{payout.method}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Type:</span>
            <p className="capitalize">{payout.type}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Arrival Date:</span>
            <p>{formatDate(payout.arrival_date * 1000)}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Automatic:</span>
            <p>{payout.automatic ? 'Yes' : 'No'}</p>
          </div>
          <div>
            <span className="text-muted-foreground">Live Mode:</span>
            <p>{payout.livemode ? 'Yes' : 'No'}</p>
          </div>
        </div>

        {payout.description && (
          <div className="mt-4">
            <span className="text-muted-foreground text-sm">Description:</span>
            <p className="text-sm">{payout.description}</p>
          </div>
        )}

        {payout.failure_message && (
          <Alert className="mt-4">
            <AlertDescription className="text-destructive">
              {payout.failure_message}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

export default function PayoutsPage() {
  const { user } = useAuth();
  const { payouts, loading, error, hasMore, totalCount, loadMorePayouts } = useAllPayouts();
  const [statusFilter, setStatusFilter] = useState('all');
  const [appFilter, setAppFilter] = useState('all');

  // Get unique apps for filter
  const uniqueApps = Array.from(new Set(payouts.map(p => p.appName))).sort();

  // Filter payouts based on selected filters
  const filteredPayouts = payouts.filter(payoutData => {
    const { payout, appName } = payoutData;
    
    if (statusFilter !== 'all' && payout.status !== statusFilter) return false;
    if (appFilter !== 'all' && appName !== appFilter) return false;
    
    return true;
  });

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">All App Payouts</h1>
          <p className="text-muted-foreground">
            View payout information for all paid apps
          </p>
        </div>
        
        {/* Loading Total Amount Card */}
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <Skeleton className="h-6 w-48 mb-2" />
                <Skeleton className="h-4 w-64" />
              </div>
              <div className="text-right">
                <Skeleton className="h-10 w-32 mb-2" />
                <Skeleton className="h-4 w-20" />
              </div>
            </div>
          </CardContent>
        </Card>
        
        <div className="space-y-4">
          {[...Array(3)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between mb-4">
                  <Skeleton className="h-6 w-32" />
                  <Skeleton className="h-6 w-16" />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-24" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold">All App Payouts</h1>
          <p className="text-muted-foreground">
            View payout information for all paid apps
          </p>
        </div>
        <Alert>
          <AlertDescription className="text-destructive">
            {error}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">All App Payouts</h1>
          <p className="text-muted-foreground">
            View payout information for all paid apps ({totalCount} total payouts)
          </p>
        </div>
        <div className="flex gap-2">

          <Button variant="outline" size="sm">
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Total Payout Amount Card */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold mb-1">Total Payout Amount</h3>
              <p className="text-sm text-muted-foreground">All time payouts across all apps</p>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold">
                {formatCurrency(
                  payouts.reduce((total, payoutData) => total + payoutData.payout.amount, 0) / 100
                )}
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {payouts.length} payout{payouts.length !== 1 ? 's' : ''}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-2">Status</label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="paid">Paid</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="in_transit">In Transit</SelectItem>
                  <SelectItem value="canceled">Canceled</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-2">App</label>
              <Select value={appFilter} onValueChange={setAppFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="All Apps" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Apps</SelectItem>
                  {uniqueApps.map(appName => (
                    <SelectItem key={appName} value={appName}>
                      {appName}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Payouts List */}
      {filteredPayouts.length === 0 ? (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <DollarSign className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No Payouts Found</h3>
              <p className="text-muted-foreground">
                {payouts.length === 0 
                  ? "No payouts have been made yet, or no apps have connected Stripe accounts."
                  : "No payouts match the current filters."
                }
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredPayouts.map((payoutData) => (
            <PayoutCard key={payoutData.payout.id} payoutData={payoutData} />
          ))}
          
          {hasMore && (
            <div className="text-center pt-4">
              <Button onClick={loadMorePayouts} variant="outline">
                Load More Payouts
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
