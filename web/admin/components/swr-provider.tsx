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
        shouldRetryOnError: (error: any) => {
          // Don't retry on auth errors — re-login is needed
          if (error?.status === 401 || error?.status === 403) return false;
          return true;
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
