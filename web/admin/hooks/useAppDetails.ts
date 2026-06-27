'use client';

import useSWR from 'swr';
import { useAuthToken, authenticatedFetcher } from '@/hooks/useAuthToken';

// Define a type for the detailed app data. Adjust as per your Firestore structure.
// For now, using a generic Record.
export interface OmiAppDetailedData extends Record<string, any> {
  id: string; // Assuming an id field exists or you add it after fetching
  name?: string;
  // Add other expected fields from plugins_data/{app_id}
}

export function useAppDetails(appId: string | null) {
  const { token, loading: tokenLoading } = useAuthToken();

  // Construct SWR key: only fetch if appId and token are available
  const swrKey = appId && token ? [`/api/omi/apps/${appId}/details`, token] : null;

  const { data, error, isLoading, mutate } = useSWR<OmiAppDetailedData, Error>(swrKey, authenticatedFetcher, {
    revalidateOnFocus: false,
  });

  return {
    appDetails: data,
    isLoadingDetails: appId ? tokenLoading || isLoading : false,
    errorDetails: error,
    mutateDetails: mutate,
  };
}
