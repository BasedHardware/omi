'use client';

import useSWR from 'swr';
import { OmiApp } from '@/lib/services/omi-api/types';
import { useAuthToken, authenticatedFetcher } from '@/hooks/useAuthToken';

export function usePrivateApps() {
  const { token, loading: tokenLoading } = useAuthToken();

  const { data, error, isLoading } = useSWR<{ apps: OmiApp[] }>(
    token ? ['/api/omi/private-apps', token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  return {
    privateApps: data?.apps ?? [],
    isLoadingPrivate: tokenLoading || isLoading,
    errorPrivate: error ?? null,
  };
}
