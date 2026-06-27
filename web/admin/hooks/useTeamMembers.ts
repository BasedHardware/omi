'use client';

import useSWR from 'swr';
import { useAuthToken, authenticatedFetcher } from '@/hooks/useAuthToken';

export interface TeamMember {
  id: string;
  name: string;
  role: string;
  email: string;
  createdAt?: any;
}

export function useTeamMembers() {
  const { token, loading: tokenLoading } = useAuthToken();

  const { data, error, isLoading } = useSWR<{ teamMembers: TeamMember[] }>(
    token ? ['/api/omi/team-members', token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );

  return {
    teamMembers: data?.teamMembers ?? [],
    isLoading: tokenLoading || isLoading,
    error: error ?? null,
  };
}
