'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/components/auth-provider';

/**
 * Shared hook that retrieves a Firebase ID token for authenticated API requests.
 * Returns { token, loading } — pass `token` into SWR keys or fetch headers.
 */
export function useAuthToken() {
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
          console.error('Error getting ID token:', error);
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

  return { token, loading: authLoading || tokenLoading };
}

/**
 * Authenticated fetcher for SWR — expects key to be [url, token].
 */
export const authenticatedFetcher = async ([url, token]: [string, string]) => {
  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const error = new Error('An error occurred while fetching the data.');
    try {
      (error as any).info = await response.json();
    } catch {
      (error as any).info = { message: 'Could not parse error JSON.' };
    }
    (error as any).status = response.status;
    throw error;
  }
  return response.json();
};

/**
 * Hook that returns a stable fetch wrapper adding the Bearer token.
 * Uses a ref so the callback identity never changes — safe for useEffect deps.
 */
export function useAuthFetch() {
  const { token } = useAuthToken();
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const fetchWithAuth = useCallback(async (url: string, init?: RequestInit) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string>),
    };
    if (tokenRef.current) {
      headers['Authorization'] = `Bearer ${tokenRef.current}`;
    }
    return fetch(url, { ...init, headers });
  }, []);

  return { fetchWithAuth, token };
}
