'use client';

import useSWR from 'swr';
import { useAuth } from '@/components/auth-provider';
import { OmiApp } from '@/lib/services/omi-api/types';

// Define the fetcher function
const fetcher = async ([url, token]: [string, string | null]) => {
  if (!token) {
    // Don't fetch if token isn't available yet
    // SWR will automatically retry when the key (which includes the token) changes
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
    } catch (e) {
      // Ignore if response is not JSON
    } 
    const error = new Error(errorMsg);
    // Attach extra info to the error object if needed
    // error.info = await response.json();
    // error.status = response.status;
    throw error;
  }

  return response.json();
};

export function useApps() {
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
                setToken(null); // Ensure token is null on error
            } finally {
                setTokenLoading(false);
            }
        } else if (!authLoading) {
            // If auth is done loading and there's no user, token is not applicable
            setToken(null);
            setTokenLoading(false);
        }
    };
    getToken();
  }, [user, authLoading]);

  // Use the token directly in the key. SWR revalidates when the key changes.
  // Pass null as token if it's loading or not available to pause fetching.
  const swrKey = tokenLoading ? null : ['/api/omi/apps', token];

  const { data, error, isLoading, mutate } = useSWR<OmiApp[], Error>(
    swrKey, 
    fetcher, 
    {
      // Optional SWR configuration
      revalidateOnFocus: false, // Adjust as needed
      // You might want to add error retry options here
    }
  );

  return {
    apps: data,
    isLoading: authLoading || tokenLoading || isLoading, // Combined loading state
    error: error,
    mutate, // Function to manually trigger revalidation
  };
}

// Add necessary imports for useState and useEffect
import { useState, useEffect } from 'react'; 