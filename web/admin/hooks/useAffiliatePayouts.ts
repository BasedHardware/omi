'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAuthFetch } from '@/hooks/useAuthToken';

export interface AffiliatePayout {
  affiliate_id: number;
  name: string;
  email: string;
  ref_code: string;
  pending_amount: number;
  total_earned: number;
  total_paid: number;
  payment_method: string;
  stripe_account_id: string | null;
  total_orders: number;
  ad_orders: number;
  organic_orders: number;
  sales_commission: number;
}

export function useAffiliatePayouts() {
  const { fetchWithAuth, token } = useAuthFetch();
  const [affiliates, setAffiliates] = useState<AffiliatePayout[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPayouts = useCallback(async () => {
    if (!token) return;
    try {
      setLoading(true);
      setError(null);

      const response = await fetchWithAuth('/api/omi/affiliate-payouts?action=pending');
      if (!response.ok) {
        throw new Error('Failed to fetch affiliate payouts');
      }

      const data = await response.json();
      setAffiliates(data.affiliates || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load payouts');
    } finally {
      setLoading(false);
    }
  }, [token, fetchWithAuth]);

  useEffect(() => {
    loadPayouts();
  }, [loadPayouts]);

  const transfer = async (affiliateId: number) => {
    const response = await fetchWithAuth('/api/omi/affiliate-payouts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'transfer',
        affiliate_id: affiliateId,
      }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || 'Transfer failed');
    }

    return response.json();
  };

  return {
    affiliates,
    loading,
    error,
    refresh: loadPayouts,
    transfer,
  };
}
