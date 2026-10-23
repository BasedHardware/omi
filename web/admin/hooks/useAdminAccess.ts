"use client";

import useSWR from "swr";
import { useAuthToken, authenticatedFetcher } from "@/hooks/useAuthToken";
import type { AccessKind, RoleId, Scope } from "@/lib/admin-access";

export interface AdminAccess {
  uid: string;
  kind: AccessKind;
  role: RoleId | null;
  roleLabel: string;
  scopes: Scope[];
}

/**
 * The signed-in admin's own scopes, for hiding what they cannot use. The
 * server's requireScope is the authority; this only shapes the UI.
 */
export function useAdminAccess() {
  const { token, loading: tokenLoading } = useAuthToken();
  const { data, error, isLoading } = useSWR<AdminAccess>(
    token ? ["/api/omi/access", token] : null,
    authenticatedFetcher,
    // Roles can change while someone is signed in; follow them without a reload.
    { revalidateOnFocus: true, refreshInterval: 60_000 }
  );
  return {
    access: data ?? null,
    isLoading: tokenLoading || isLoading,
    error: error ?? null,
    can: (scope: Scope) => data?.scopes.includes(scope) ?? false,
  };
}
