'use client';

import { SWRConfig } from 'swr';
import { ReactNode } from 'react';

export function SWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        errorRetryCount: 3,
        errorRetryInterval: 3000,
        dedupingInterval: 5000,
        revalidateOnReconnect: true,
        onErrorRetry: (error, _key, _config, revalidate, { retryCount }) => {
          // Don't retry on auth errors — re-login is needed
          if (error?.status === 401 || error?.status === 403) return;
          if (retryCount >= 3) return;
          // Exponential backoff: 2s, 4s, 8s
          setTimeout(() => revalidate({ retryCount }), Math.min(1000 * 2 ** retryCount, 30000));
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
