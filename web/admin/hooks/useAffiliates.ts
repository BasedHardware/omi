'use client';

import { useCallback, useEffect, useState } from 'react';
import { useAuthFetch } from '@/hooks/useAuthToken';

export interface Affiliate {
  id: number;
  name: string;
  first_name?: string;
  last_name?: string;
  email: string;
  ref_code: string;
  coupon?: string;
  status?: string;
  phone?: string;
  country?: string;
  city?: string;
  website?: string;
  payment_method?: string | null;
  created_at?: string;
  updated_at?: string;
  group_id?: number;
}

export interface AffiliateDetail extends Affiliate {
  facebook?: string;
  twitter?: string;
  instagram?: string;
  address_1?: string;
  state?: string;
  zip_code?: string;
  payment_details?: Record<string, string>;
  comments?: string;
  personal_message?: string;
  registration_ip?: string;
  ref_codes?: Array<{ ref_code: string }>;
  coupons?: Array<{ coupon: string }>;
}

export interface AffiliateStats {
  total_orders: number;
  pending_amount: number;
  total_earned: number;
  total_paid: number;
}

export interface AffiliateFilters {
  status?: string;
  search?: string;
}

const PAGE_SIZE = 50;

export function useAffiliates(filters: AffiliateFilters) {
  const { fetchWithAuth, token } = useAuthFetch();
  const [affiliates, setAffiliates] = useState<Affiliate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);

  const fetchPage = useCallback(
    async (nextOffset: number, replace: boolean) => {
      if (!token) return;
      const params = new URLSearchParams({
        action: 'list',
        limit: String(PAGE_SIZE),
        offset: String(nextOffset),
      });
      if (filters.status) params.set('status', filters.status);
      if (filters.search) params.set('search', filters.search);

      const setLoader = replace ? setLoading : setLoadingMore;
      setLoader(true);
      setError(null);
      try {
        const res = await fetchWithAuth(`/api/omi/affiliates?${params.toString()}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || 'Failed to load affiliates');
        }
        const data = await res.json();
        const list: Affiliate[] = data.affiliates || [];
        setAffiliates((prev) => (replace ? list : [...prev, ...list]));
        setHasMore(!!data.has_more);
        setOffset(nextOffset + list.length);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load affiliates');
      } finally {
        setLoader(false);
      }
    },
    [token, fetchWithAuth, filters.status, filters.search]
  );

  useEffect(() => {
    setOffset(0);
    fetchPage(0, true);
  }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (!hasMore || loadingMore || loading) return;
    fetchPage(offset, false);
  }, [hasMore, loadingMore, loading, offset, fetchPage]);

  const refresh = useCallback(() => {
    setOffset(0);
    fetchPage(0, true);
  }, [fetchPage]);

  return { affiliates, loading, loadingMore, error, hasMore, loadMore, refresh };
}

export function useAffiliateDetail() {
  const { fetchWithAuth } = useAuthFetch();

  const load = useCallback(
    async (id: number): Promise<{ affiliate: AffiliateDetail; stats: AffiliateStats }> => {
      const res = await fetchWithAuth(`/api/omi/affiliates?action=detail&id=${id}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to load affiliate');
      }
      return res.json();
    },
    [fetchWithAuth]
  );

  return { load };
}
