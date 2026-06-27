'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useAffiliates, Affiliate } from '@/hooks/useAffiliates';
import { RefreshCw, Search, Loader2 } from 'lucide-react';

const STATUS_FILTERS = [
  { value: 'all', label: 'All statuses' },
  { value: 'approved', label: 'Approved' },
  { value: 'pending', label: 'Pending' },
  { value: 'blocked', label: 'Blocked' },
];

function statusBadge(status: string | undefined) {
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
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function AllAffiliatesTab({
  onSelect,
}: {
  onSelect: (affiliate: Affiliate) => void;
}) {
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const { affiliates, loading, loadingMore, error, hasMore, loadMore, refresh } = useAffiliates({
    status: status === 'all' ? undefined : status,
    search: search || undefined,
  });

  // Debounce the search input so we don't fire a request on every keystroke
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, email, ref code, or coupon"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-[160px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((f) => (
              <SelectItem key={f.value} value={f.value}>
                {f.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <Card>
          <CardContent className="pt-6 text-center text-destructive">{error}</CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Affiliate</TableHead>
                <TableHead>Ref Code</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Country</TableHead>
                <TableHead>Payment</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && affiliates.length === 0 ? (
                [...Array(8)].map((_, i) => (
                  <TableRow key={i}>
                    {[...Array(6)].map((_, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-24" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : affiliates.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    No affiliates found
                  </TableCell>
                </TableRow>
              ) : (
                affiliates.map((a) => (
                  <TableRow
                    key={a.id}
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => onSelect(a)}
                  >
                    <TableCell>
                      <div>
                        <p className="font-medium">{a.name || '—'}</p>
                        <p className="text-xs text-muted-foreground">{a.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <code className="text-xs">{a.ref_code || '—'}</code>
                    </TableCell>
                    <TableCell>{statusBadge(a.status)}</TableCell>
                    <TableCell className="text-sm">{a.country || '—'}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {a.payment_method || 'none'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(a.created_at)}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {loading && affiliates.length === 0
            ? 'Loading…'
            : `${affiliates.length} affiliate${affiliates.length === 1 ? '' : 's'} loaded`}
        </span>
        {hasMore && !search && (
          <Button variant="outline" size="sm" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : null}
            Load more
          </Button>
        )}
      </div>
    </div>
  );
}
