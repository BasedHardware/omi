"use client";

import useSWR from "swr";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";

/**
 * Whether the server allows the local coding-agent endpoint
 * (GET /api/omi/agent/customize). False while unknown: the server's
 * requireScope stays the authority; this only shapes the UI, which hides
 * the agent widget entirely while the endpoint is disabled.
 */
export function useLocalAgentEnabled() {
  const { token } = useAuthToken();
  const { data } = useSWR<{ enabled: boolean }>(
    token ? ["/api/omi/agent/customize", token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );
  return data?.enabled === true;
}
