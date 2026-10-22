"use client";

import useSWR from "swr";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";
import type { RosterMember, AuditEntry } from "@/lib/team/roster";
import type { Proposal } from "@/lib/team/proposals";
import type { Scope } from "@/lib/admin-access";

export type TeamMember = RosterMember;
export type { AuditEntry, Proposal };

export interface TeamViewer {
  uid: string;
  /** `adminData/{uid}.owner === true` (any number of owners); only owners manage deputies. */
  isOwner: boolean;
  /** team:manage — change roles, remove people, approve proposals. */
  canManage: boolean;
  canInvite: boolean;
  canRemove: boolean;
  scopes: Scope[];
}

function useTeamResource<T>(url: string) {
  const { token, loading: tokenLoading } = useAuthToken();
  const { data, error, isLoading, mutate } = useSWR<T>(
    token ? [url, token] : null,
    authenticatedFetcher,
    { revalidateOnFocus: false }
  );
  return {
    data,
    isLoading: tokenLoading || isLoading,
    error: error ?? null,
    mutate,
  };
}

export function useTeamMembers() {
  const { data, ...rest } = useTeamResource<{
    teamMembers: TeamMember[];
    viewer?: TeamViewer;
  }>("/api/omi/team-members");
  return {
    teamMembers: data?.teamMembers ?? [],
    viewer: data?.viewer ?? null,
    ...rest,
  };
}

export function useTeamProposals() {
  const { data, ...rest } = useTeamResource<{ proposals: Proposal[] }>(
    "/api/omi/team-members/proposals"
  );
  return { proposals: data?.proposals ?? [], ...rest };
}

export function useTeamAudit() {
  const { data, ...rest } = useTeamResource<{
    entries: (AuditEntry & { id: string })[];
  }>("/api/omi/team-members/audit");
  return { entries: data?.entries ?? [], ...rest };
}
