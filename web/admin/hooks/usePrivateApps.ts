'use client';

import useSWR from 'swr';
import { OmiApp } from '@/lib/services/omi-api/types';
import { useAuthToken, authenticatedFetcher, AUTH_SCOPE } from '@/hooks/useAuthToken';

export function usePrivateApps() {
  const { token, loading: tokenLoading } = useAuthToken();

  const { data, error, isLoading } = useSWR<{ apps: OmiApp[] }>(
    token ? ['/api/omi/private-apps', AUTH_SCOPE] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  return {
    privateApps: data?.apps ?? [],
    isLoadingPrivate: tokenLoading || isLoading,
    errorPrivate: error ?? null,
  };
}
