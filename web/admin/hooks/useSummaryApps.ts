'use client';

import useSWR from 'swr';
import { useAuth } from '@/components/auth-provider';

const fetcher = async ([url, token]: [string, string | null]) => {
  if (!token) {
    throw new Error('Auth token not available');
  }

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
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

export function useSummaryApps() {
  const { user, loading: authLoading } = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(true);

  useEffect(() => {
    const run = async () => {
      if (user) {
        try {
          const idToken = await user.getIdToken();
          setToken(idToken);
        } catch (e) {
          console.error('getIdToken error', e);
          setToken(null);
        } finally {
          setTokenLoading(false);
        }
      } else if (!authLoading) {
        setToken(null);
        setTokenLoading(false);
      }
    };
    run();
  }, [user, authLoading]);

  const swrKey = tokenLoading ? null : ['/api/omi/summary-apps', token];
  const { data, error, isLoading, mutate } = useSWR<any[]>(swrKey, fetcher, {
    revalidateOnFocus: false,
  });

  const addSummaryApp = async (appId: string) => {
    if (!token) {
      throw new Error('Auth token not available');
    }

    const res = await fetch('/api/omi/summary-apps', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
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
    if (!token) {
      throw new Error('Auth token not available');
    }

    const res = await fetch('/api/omi/summary-apps', {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
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
    isLoading: authLoading || tokenLoading || isLoading,
    error,
    mutate,
    addSummaryApp,
    removeSummaryApp,
  };
}

import { useEffect, useState } from 'react';

