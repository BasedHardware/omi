'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/components/auth-provider';

// Module-level callback so the standalone authenticatedFetcher can
// trigger a token force-refresh on 401 without being a React hook.
// Multiple useAuthToken() instances may be mounted simultaneously —
// ref-counting ensures the callback survives until the last one unmounts.
let _forceRefreshCallback: (() => Promise<string | null>) | null = null;
let _forceRefreshRefCount = 0;

const REQUEST_TIMEOUT_MS = 300_000;

/** Fetch with a timeout. Aborts the request if it exceeds the deadline. */
function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { ...init, signal: controller.signal }).finally(() => clearTimeout(timer));
}

/** Build a typed error from a non-ok response. */
async function buildResponseError(response: Response): Promise<Error> {
  const error = new Error('An error occurred while fetching the data.');
  try {
    (error as any).info = await response.json();
  } catch {
    (error as any).info = { message: 'Could not parse error JSON.' };
  }
  (error as any).status = response.status;
  return error;
}

/**
 * Shared hook that retrieves a Firebase ID token for authenticated API requests.
 * Returns { token, loading, forceRefresh } — pass `token` into SWR keys or fetch headers.
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

    // Refresh token every 10 minutes to prevent stale-token 401s.
    // Firebase ID tokens expire after 1 hour; getIdToken() returns
    // a fresh token when the cached one is close to expiry.
    // On failure, keep the existing token rather than nulling it —
    // a stale token that triggers a 401 retry is better than no token.
    if (user) {
      const interval = setInterval(() => {
        user.getIdToken().then(setToken).catch(() => {});
      }, 10 * 60 * 1000);
      return () => clearInterval(interval);
    }
  }, [user, authLoading]);

  /** Force-refresh the token (e.g. after a 401). Returns the new token or null. */
  const forceRefresh = useCallback(async (): Promise<string | null> => {
    if (!user) return null;
    try {
      const freshToken = await user.getIdToken(true);
      setToken(freshToken);
      return freshToken;
    } catch {
      return null;
    }
  }, [user]);

  // Register the forceRefresh callback at module level so authenticatedFetcher
  // (a non-hook standalone function) can trigger token refresh on 401.
  // Ref-counted: multiple hooks can mount/unmount independently without
  // clearing the callback while other instances are still alive.
  useEffect(() => {
    _forceRefreshCallback = forceRefresh;
    _forceRefreshRefCount++;
    return () => {
      _forceRefreshRefCount--;
      if (_forceRefreshRefCount === 0) {
        _forceRefreshCallback = null;
      }
    };
  }, [forceRefresh]);

  return { token, loading: authLoading || tokenLoading, forceRefresh };
}

/**
 * Authenticated fetcher for SWR — expects key to be [url, token].
 * Includes 5min timeout.
 */
export const authenticatedFetcher = async ([url, token]: [string, string]) => {
  const response = await fetchWithTimeout(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  // On 401, force-refresh the token and replay once.
  // Without this, SWR skips retry on 401 (see swr-provider onErrorRetry)
  // and the dashboard card stays broken until a manual page reload.
  if (response.status === 401 && _forceRefreshCallback) {
    const freshToken = await _forceRefreshCallback();
    if (freshToken) {
      const retryResponse = await fetchWithTimeout(url, {
        headers: {
          Authorization: `Bearer ${freshToken}`,
          'Content-Type': 'application/json',
        },
      });
      if (!retryResponse.ok) {
        throw await buildResponseError(retryResponse);
      }
      return retryResponse.json();
    }
  }

  if (!response.ok) {
    throw await buildResponseError(response);
  }
  return response.json();
};

/**
 * Hook that returns a stable fetch wrapper adding the Bearer token.
 * Uses a ref so the callback identity never changes — safe for useEffect deps.
 *
 * Features:
 * - 5min request timeout
 * - Auto-refresh token and replay once on 401
 */
export function useAuthFetch() {
  const { token, forceRefresh } = useAuthToken();
  const tokenRef = useRef(token);
  tokenRef.current = token;
  const forceRefreshRef = useRef(forceRefresh);
  forceRefreshRef.current = forceRefresh;

  const fetchWithAuth = useCallback(async (url: string, init?: RequestInit) => {
    const isFormData = init?.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers as Record<string, string>),
    };
    if (tokenRef.current) {
      headers['Authorization'] = `Bearer ${tokenRef.current}`;
    }

    const response = await fetchWithTimeout(url, { ...init, headers });

    // On 401, force-refresh the token and replay the request once
    if (response.status === 401 && tokenRef.current) {
      const freshToken = await forceRefreshRef.current();
      if (freshToken) {
        tokenRef.current = freshToken;
        headers['Authorization'] = `Bearer ${freshToken}`;
        return fetchWithTimeout(url, { ...init, headers });
      }
    }

    return response;
  }, []);

  return { fetchWithAuth, token };
}
