'use client';

import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AffiliateDetail,
  AffiliateStats,
  useAffiliateDetail,
} from '@/hooks/useAffiliates';
import { formatCurrency } from '@/lib/utils';

function statusLabel(status: string | undefined) {
  switch ((status ?? '').toLowerCase()) {
    case 'approved':
      return <Badge className="bg-green-600 hover:bg-green-600 text-white">Approved</Badge>;
    case 'pending':
      return <Badge variant="secondary">Pending</Badge>;
    case 'blocked':
      return <Badge variant="destructive">Blocked</Badge>;
    default:
      return <Badge variant="outline">{status || 'Unknown'}</Badge>;
  }
}

function formatDate(value?: string): string {
  if (!value) return '—';
  const d = new Date(value);
  if (isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right break-words max-w-[60%]">{children}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold uppercase text-muted-foreground tracking-wide mb-1.5">
        {title}
      </h3>
      <div className="divide-y">{children}</div>
    </div>
  );
}

export function AffiliateDetailDialog({
  affiliateId,
  open,
  onOpenChange,
}: {
  affiliateId: number | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { load } = useAffiliateDetail();
  const [data, setData] = useState<{ affiliate: AffiliateDetail; stats: AffiliateStats } | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !affiliateId) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    load(affiliateId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, affiliateId, load]);

  const a = data?.affiliate;
  const stats = data?.stats;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{a?.name || (loading ? 'Loading…' : 'Affiliate')}</DialogTitle>
          <DialogDescription>
            {a?.email || (loading ? '' : 'Affiliate detail')}
          </DialogDescription>
        </DialogHeader>

        {error && <div className="text-destructive text-sm">{error}</div>}

        {loading && !data && (
          <div className="space-y-4">
            {[...Array(6)].map((_, i) => (
              <Skeleton key={i} className="h-5 w-full" />
            ))}
          </div>
        )}

        {a && stats && (
          <div className="space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Pending</div>
                <div className="text-lg font-semibold">
                  {formatCurrency(stats.pending_amount)}
                </div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Earned</div>
                <div className="text-lg font-semibold">
                  {formatCurrency(stats.total_earned)}
                </div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Paid</div>
                <div className="text-lg font-semibold">{formatCurrency(stats.total_paid)}</div>
              </div>
              <div className="rounded-md border p-3">
                <div className="text-xs text-muted-foreground">Orders</div>
                <div className="text-lg font-semibold">{stats.total_orders}</div>
              </div>
            </div>

            <Section title="Profile">
              <Field label="ID">{a.id}</Field>
              <Field label="Status">{statusLabel(a.status)}</Field>
              <Field label="Ref Code">
                <code className="text-xs">{a.ref_code || '—'}</code>
              </Field>
              {a.coupon && (
                <Field label="Coupon">
                  <code className="text-xs">{a.coupon}</code>
                </Field>
              )}
              <Field label="Phone">{a.phone || '—'}</Field>
              <Field label="Joined">{formatDate(a.created_at)}</Field>
              {a.updated_at && <Field label="Updated">{formatDate(a.updated_at)}</Field>}
            </Section>

            {(a.address_1 || a.city || a.state || a.country || a.zip_code) && (
              <Section title="Location">
                {a.address_1 && <Field label="Address">{a.address_1}</Field>}
                {a.city && <Field label="City">{a.city}</Field>}
                {a.state && <Field label="State">{a.state}</Field>}
                {a.country && <Field label="Country">{a.country}</Field>}
                {a.zip_code && <Field label="ZIP">{a.zip_code}</Field>}
              </Section>
            )}

            {(a.website || a.facebook || a.twitter || a.instagram) && (
              <Section title="Web & Social">
                {a.website && <Field label="Website">{a.website}</Field>}
                {a.facebook && <Field label="Facebook">{a.facebook}</Field>}
                {a.twitter && <Field label="Twitter">{a.twitter}</Field>}
                {a.instagram && <Field label="Instagram">{a.instagram}</Field>}
              </Section>
            )}

            <Section title="Payout">
              <Field label="Method">
                <Badge variant="outline">{a.payment_method || 'none'}</Badge>
              </Field>
              {a.payment_details &&
                Object.entries(a.payment_details).map(([k, v]) => (
                  <Field key={k} label={k}>
                    <code className="text-xs">{String(v)}</code>
                  </Field>
                ))}
            </Section>

            {(a.comments || a.personal_message) && (
              <Section title="Notes">
                {a.comments && <Field label="Comments">{a.comments}</Field>}
                {a.personal_message && (
                  <Field label="Personal message">{a.personal_message}</Field>
                )}
              </Section>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
