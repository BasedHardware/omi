"use client";

import { useEffect } from "react";
import useSWR from "swr";
import { Users } from "lucide-react";

type UserGrowthResponse = {
  totalUsers: number;
  generatedAt: number;
};

const fetcher = async (url: string): Promise<UserGrowthResponse> => {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
};

export default function PublicUsersPage() {
  useEffect(() => {
    document.title = "Omi — Users";
  }, []);

  const { data, error, isLoading } = useSWR<UserGrowthResponse>(
    "/api/public/user-growth?days=1",
    fetcher,
    { revalidateOnFocus: false },
  );

  const totalUsers = data?.totalUsers;

  return (
    <div className="min-h-screen bg-background text-foreground flex items-center justify-center px-4">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="rounded-full bg-primary/10 p-3">
          <Users className="h-6 w-6 text-primary" />
        </div>
        <div className="text-sm uppercase tracking-wide text-muted-foreground">
          Omi users
        </div>
        <div className="text-7xl font-bold tracking-tight tabular-nums">
          {error
            ? "—"
            : isLoading || totalUsers == null
              ? "…"
              : totalUsers.toLocaleString()}
        </div>
      </div>
    </div>
  );
}
