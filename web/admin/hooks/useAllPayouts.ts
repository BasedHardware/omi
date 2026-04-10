'use client';

import { useState, useEffect } from 'react';
import { PayoutWithAppInfo } from '@/lib/services/omi-api/types';
import { useAuthFetch } from '@/hooks/useAuthToken';

export function useAllPayouts() {
  const { fetchWithAuth, token } = useAuthFetch();
  const [payouts, setPayouts] = useState<PayoutWithAppInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    if (!token) return;

    const loadPayouts = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await fetchWithAuth('/api/omi/all-payouts');

        if (!response.ok) {
          throw new Error('Failed to fetch payouts');
        }

        const data = await response.json();
        setPayouts(data.payouts);
        setHasMore(data.hasMore);
        setTotalCount(data.totalCount);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load payouts');
      } finally {
        setLoading(false);
      }
    };

    loadPayouts();
  }, [token, fetchWithAuth]);

  const loadMorePayouts = async () => {
    if (!token || !hasMore) return;

    try {
      const lastPayout = payouts[payouts.length - 1];

      const response = await fetchWithAuth(`/api/omi/all-payouts?starting_after=${lastPayout.payout.id}`);

      if (!response.ok) {
        throw new Error('Failed to load more payouts');
      }

      const data = await response.json();
      setPayouts((prev) => [...prev, ...data.payouts]);
      setHasMore(data.hasMore);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more payouts');
    }
  };

  return {
    payouts,
    loading,
    error,
    hasMore,
    totalCount,
    loadMorePayouts,
  };
}
