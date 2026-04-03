import { useState, useEffect } from 'react';
import { useAuth } from '@/components/auth-provider';
import { PayoutWithAppInfo } from '@/lib/services/omi-api/types';

export function useAllPayouts() {
  const { user } = useAuth();
  const [payouts, setPayouts] = useState<PayoutWithAppInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    if (!user?.uid) return;

    const loadPayouts = async () => {
      try {
        setLoading(true);
        setError(null);

        const idToken = await user.getIdToken();
        const response = await fetch('/api/omi/all-payouts', {
          headers: {
            'Authorization': `Bearer ${idToken}`,
          },
        });

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
  }, [user?.uid]);

  const loadMorePayouts = async () => {
    if (!user?.uid || !hasMore) return;

    try {
      const idToken = await user.getIdToken();
      const lastPayout = payouts[payouts.length - 1];
      
      const response = await fetch(`/api/omi/all-payouts?starting_after=${lastPayout.payout.id}`, {
        headers: {
          'Authorization': `Bearer ${idToken}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load more payouts');
      }

      const data = await response.json();
      setPayouts(prev => [...prev, ...data.payouts]);
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
