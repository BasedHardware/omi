'use client';

import useSWR from 'swr';
import { useAuth } from '@/components/auth-provider';
import { useState, useEffect } from 'react';

// Define a type for the detailed app data. Adjust as per your Firestore structure.
// For now, using a generic Record.
export interface OmiAppDetailedData extends Record<string, any> {
  id: string; // Assuming an id field exists or you add it after fetching
  name?: string;
  // Add other expected fields from plugins_data/{app_id}
}

const fetcher = async ([url, token]: [string, string | null]): Promise<OmiAppDetailedData> => {
  if (!token) {
    throw new Error('Auth token not available for fetching app details');
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

export function useAppDetails(appId: string | null) {
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
                console.error("Error getting ID token for app details:", error);
                setToken(null); 
            } finally {
                setTokenLoading(false);
            }
        } else if (!authLoading) {
            setToken(null);
            setTokenLoading(false);
        }
    };
    if (appId) { // Only try to get token if appId is present
        getToken();
    } else {
        setTokenLoading(false); // Not loading token if no appId
        setToken(null);
    }
  }, [user, authLoading, appId]);

  // Construct SWR key: only fetch if appId and token are available
  const swrKey = (appId && token && !tokenLoading) ? [`/api/omi/apps/${appId}/details`, token] : null;

  const { data, error, isLoading, mutate } = useSWR<OmiAppDetailedData, Error>(
    swrKey, 
    fetcher, 
    {
      revalidateOnFocus: false,
      // keepPreviousData: true, // Consider if you want to show stale data while new app details load
    }
  );

  return {
    appDetails: data,
    isLoadingDetails: appId ? (authLoading || tokenLoading || isLoading) : false,
    errorDetails: error,
    mutateDetails: mutate,
  };
} 