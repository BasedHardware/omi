'use client';

import useSWR from 'swr';
import { useAuthToken, authenticatedFetcher, useAuthFetch } from '@/hooks/useAuthToken';

export function useSummaryApps() {
  const { token, loading: tokenLoading } = useAuthToken();
  const { fetchWithAuth } = useAuthFetch();

  const swrKey = token ? ['/api/omi/summary-apps', token] : null;
  const { data, error, isLoading, mutate } = useSWR<any[]>(swrKey, authenticatedFetcher, {
    revalidateOnFocus: false,
  });

  const addSummaryApp = async (appId: string) => {
    const res = await fetchWithAuth('/api/omi/summary-apps', {
      method: 'POST',
      body: JSON.stringify({ appId }),
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        message = j?.error || j?.message || message;
      } catch {}
      throw new Error(message);
    }

    return res.json();
  };

  const removeSummaryApp = async (appId: string) => {
    const res = await fetchWithAuth('/api/omi/summary-apps', {
      method: 'DELETE',
      body: JSON.stringify({ appId }),
    });

    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        message = j?.error || j?.message || message;
      } catch {}
      throw new Error(message);
    }

    return res.json();
  };

  return {
    summaryApps: data,
    isLoading: tokenLoading || isLoading,
    error,
    mutate,
    addSummaryApp,
    removeSummaryApp,
  };
}
