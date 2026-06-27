'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAffiliatePayouts, AffiliatePayout } from '@/hooks/useAffiliatePayouts';
import { formatCurrency } from '@/lib/utils';
import {
  DollarSign,
  Users,
  RefreshCw,
  Send,
  AlertTriangle,
  CheckCircle,
  Megaphone,
  MousePointerClick,
} from 'lucide-react';
import { toast } from 'sonner';

export function PendingPayoutsTab() {
  const { affiliates, loading, error, refresh, transfer } = useAffiliatePayouts();
  const [transferring, setTransferring] = useState<number | null>(null);
  const [confirmDialog, setConfirmDialog] = useState<AffiliatePayout | null>(null);

  const totalPending = affiliates.reduce((sum, a) => sum + a.pending_amount, 0);
  const withStripe = affiliates.filter((a) => a.stripe_account_id);
  const withoutStripe = affiliates.filter((a) => !a.stripe_account_id);

  const handleTransfer = async (affiliate: AffiliatePayout) => {
    if (!affiliate.stripe_account_id) {
      toast.error('Affiliate has no Stripe account connected');
      return;
    }
    setTransferring(affiliate.affiliate_id);
    try {
      const result = await transfer(affiliate.affiliate_id);
      if (result.partial) {
        toast.warning(result.warning);
      } else {
        toast.success(
          `Transferred ${formatCurrency(affiliate.pending_amount)} to ${affiliate.name} (${result.transfer_id})`
        );
      }
      setConfirmDialog(null);
      refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Transfer failed');
    } finally {
      setTransferring(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <Card key={i}>
              <CardContent className="pt-6">
                <Skeleton className="h-8 w-32 mb-2" />
                <Skeleton className="h-4 w-20" />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="pt-6">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full mb-2" />
            ))}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="pt-6 text-center text-destructive">{error}</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={refresh}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatCurrency(totalPending)}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {affiliates.length} affiliates above $10 minimum
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Stripe Connected</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{withStripe.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Ready for transfer</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">No Stripe</CardTitle>
            <AlertTriangle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{withoutStripe.length}</div>
            <p className="text-xs text-muted-foreground mt-1">Need to connect Stripe first</p>
          </CardContent>
        </Card>
      </div>

      {withStripe.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Send className="h-5 w-5" />
              Ready for Transfer ({withStripe.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Affiliate</TableHead>
                  <TableHead>Ref Code</TableHead>
                  <TableHead>Orders</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Earned</TableHead>
                  <TableHead className="text-right">Paid</TableHead>
                  <TableHead className="text-right">Pending</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {withStripe.map((a) => (
                  <TableRow key={a.affiliate_id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{a.name}</p>
                        <p className="text-xs text-muted-foreground">{a.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">{a.ref_code}</code>
                    </TableCell>
                    <TableCell>{a.total_orders}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {a.organic_orders > 0 && (
                          <Badge variant="secondary" className="text-xs">
                            <MousePointerClick className="h-3 w-3 mr-1" />
                            {a.organic_orders}
                          </Badge>
                        )}
                        {a.ad_orders > 0 && (
                          <Badge variant="outline" className="text-xs">
                            <Megaphone className="h-3 w-3 mr-1" />
                            {a.ad_orders}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">{formatCurrency(a.total_earned)}</TableCell>
                    <TableCell className="text-right">{formatCurrency(a.total_paid)}</TableCell>
                    <TableCell className="text-right font-medium">
                      {formatCurrency(a.pending_amount)}
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        onClick={() => setConfirmDialog(a)}
                        disabled={transferring === a.affiliate_id}
                      >
                        {transferring === a.affiliate_id ? (
                          <RefreshCw className="h-3 w-3 mr-1 animate-spin" />
                        ) : (
                          <Send className="h-3 w-3 mr-1" />
                        )}
                        Transfer
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {withoutStripe.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              No Stripe Connected ({withoutStripe.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Affiliate</TableHead>
                  <TableHead>Ref Code</TableHead>
                  <TableHead>Payment Method</TableHead>
                  <TableHead>Orders</TableHead>
                  <TableHead className="text-right">Pending</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {withoutStripe.map((a) => (
                  <TableRow key={a.affiliate_id}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{a.name}</p>
                        <p className="text-xs text-muted-foreground">{a.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">{a.ref_code}</code>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{a.payment_method || 'none'}</Badge>
                    </TableCell>
                    <TableCell>{a.total_orders}</TableCell>
                    <TableCell className="text-right font-medium">
                      {formatCurrency(a.pending_amount)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Dialog open={!!confirmDialog} onOpenChange={() => setConfirmDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Transfer</DialogTitle>
            <DialogDescription>
              Transfer {confirmDialog && formatCurrency(confirmDialog.pending_amount)} to{' '}
              {confirmDialog?.name}?
            </DialogDescription>
          </DialogHeader>
          {confirmDialog && (
            <div className="space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Affiliate</span>
                <span className="font-medium">{confirmDialog.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Email</span>
                <span>{confirmDialog.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Stripe Account</span>
                <code className="text-xs">{confirmDialog.stripe_account_id}</code>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Amount</span>
                <span className="font-bold text-lg">
                  {formatCurrency(confirmDialog.pending_amount)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Orders</span>
                <span>
                  {confirmDialog.total_orders} total ({confirmDialog.organic_orders} organic,{' '}
                  {confirmDialog.ad_orders} from ads)
                </span>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDialog(null)}>
              Cancel
            </Button>
            <Button
              onClick={() => confirmDialog && handleTransfer(confirmDialog)}
              disabled={transferring !== null}
            >
              {transferring ? (
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Send className="h-4 w-4 mr-2" />
              )}
              Confirm Transfer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
