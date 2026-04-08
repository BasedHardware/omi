'use client';

import useSWR from 'swr';
import { OmiApp } from '@/lib/services/omi-api/types';
import { useAuthToken, authenticatedFetcher } from '@/hooks/useAuthToken';

export function useApps() {
  const { token, loading: tokenLoading } = useAuthToken();

  const swrKey = token ? ['/api/omi/apps', token] : null;

  const { data, error, isLoading, mutate } = useSWR<OmiApp[], Error>(swrKey, authenticatedFetcher, {
    revalidateOnFocus: false,
  });

  return {
    apps: data,
    isLoading: tokenLoading || isLoading,
    error: error,
    mutate,
  };
}
