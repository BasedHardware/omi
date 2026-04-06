'use client';

import useSWR from 'swr';
import { useAuth } from '@/components/auth-provider';
import { OmiApp } from '@/lib/services/omi-api/types';
import { useState, useEffect } from 'react';

// Define the fetcher function (can potentially be shared with useApps)
const fetcher = async ([url, token]: [string, string | null]) => {
  if (!token) {
    throw new Error('Auth token not available');
  }
  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });
  if (!response.ok) {
    let errorMsg = `HTTP error! status: ${response.status}`;
    try {
      const errorData = await response.json();
      errorMsg = errorData.error || errorData.message || errorMsg;
    } catch (e) { /* Ignore */ } 
    const error = new Error(errorMsg);
    throw error;
  }
  return response.json();
};

export function useUnapprovedApps() {
  const { user, loading: authLoading } = useAuth();
  const [token, setToken] = useState<string | null>(null);
  const [tokenLoading, setTokenLoading] = useState(true);

  useEffect(() => {
    const getToken = async () => {
        if (user) {
            try {
                const idToken = await user.getIdToken();
                setToken(idToken);
            } catch (error) {
                console.error("Error getting ID token:", error);
                setToken(null); 
            } finally {
                setTokenLoading(false);
            }
        } else if (!authLoading) {
            setToken(null);
            setTokenLoading(false);
        }
    };
    getToken();
  }, [user, authLoading]);

  // Target the new API route
  const swrKey = tokenLoading ? null : ['/api/omi/apps/unapproved', token];

  const { data, error, isLoading, mutate } = useSWR<OmiApp[], Error>(
    swrKey, 
    fetcher, 
    { revalidateOnFocus: false }
  );

  return {
    unapprovedApps: data,
    isLoadingUnapproved: authLoading || tokenLoading || isLoading,
    errorUnapproved: error,
    mutateUnapproved: mutate,
  };
} 