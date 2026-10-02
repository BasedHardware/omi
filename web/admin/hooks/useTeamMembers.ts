"use client";

import useSWR from "swr";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  email: string;
  createdAt?: any;
  owner?: boolean;
}

export interface TeamViewer {
  uid: string;
  /** True only for the workspace owner (`adminData/{uid}.owner === true`). */
  canRemove: boolean;
}

export function useTeamMembers() {
  const { token, loading: tokenLoading } = useAuthToken();

  const { data, error, isLoading, mutate } = useSWR<{
    teamMembers: TeamMember[];
    viewer?: TeamViewer;
  }>(token ? ["/api/omi/team-members", token] : null, authenticatedFetcher, {
    revalidateOnFocus: false,
  });

  return {
    teamMembers: data?.teamMembers ?? [],
    viewer: data?.viewer ?? null,
    isLoading: tokenLoading || isLoading,
    error: error ?? null,
    mutate,
  };
}
