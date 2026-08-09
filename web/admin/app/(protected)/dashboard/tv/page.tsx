"use client";

import { useCallback } from "react";
import { TvBoard } from "@/components/dashboard/tv-board";
import { useAuthToken } from "@/hooks/useAuthToken";

export default function DashboardTvPage() {
  const { token } = useAuthToken();
  const getToken = useCallback(async () => token, [token]);

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      <TvBoard getToken={getToken} showAdminChrome />
    </div>
  );
}
