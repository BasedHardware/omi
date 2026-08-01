'use client';

import useSWR from 'swr';
import { OmiApp } from '@/lib/services/omi-api/types';
import { useAuthToken, authenticatedFetcher, AUTH_SCOPE } from '@/hooks/useAuthToken';

export function useUnapprovedApps() {
  const { token, loading: tokenLoading } = useAuthToken();

  const swrKey = token ? ['/api/omi/apps/unapproved', AUTH_SCOPE] : null;

  const { data, error, isLoading, mutate } = useSWR<OmiApp[], Error>(swrKey, authenticatedFetcher, {
    revalidateOnFocus: false,
  });

  return {
    unapprovedApps: data,
    isLoadingUnapproved: tokenLoading || isLoading,
    errorUnapproved: error,
    mutateUnapproved: mutate,
  };
}
