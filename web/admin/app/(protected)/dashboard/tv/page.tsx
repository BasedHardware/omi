"use client";

import { useCallback } from "react";
import Link from "next/link";
import { TvBoard } from "@/components/dashboard/tv-board";
import { useAuthToken } from "@/hooks/useAuthToken";
import { Button } from "@/components/ui/button";

export default function DashboardTvPage() {
  const { token } = useAuthToken();

  const getToken = useCallback(async () => token, [token]);

  return (
    <div className="relative">
      <div className="absolute top-3 right-4 z-10 flex gap-2">
        <Button asChild variant="secondary" size="sm">
          <Link href="/dashboard/tv-links">TV links</Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link href="/dashboard">Exit TV</Link>
        </Button>
      </div>
      <TvBoard getToken={getToken} />
    </div>
  );
}
