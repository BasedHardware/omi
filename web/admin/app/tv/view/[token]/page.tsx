"use client";

import { useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import { TvBoard } from "@/components/dashboard/tv-board";

/**
 * Public kiosk TV surface. Auth is the path token (capability URL).
 * Does not use the admin shell or Firebase login.
 */
export default function PublicTvViewPage() {
  const params = useParams();
  const token = useMemo(() => {
    const t = params?.token;
    return typeof t === "string" ? t : Array.isArray(t) ? t[0] : "";
  }, [params]);

  const getToken = useCallback(async () => token || null, [token]);

  if (!token) {
    return (
      <div className="min-h-screen grid place-items-center bg-slate-950 text-slate-200">
        Missing TV token
      </div>
    );
  }

  return <TvBoard getToken={getToken} kioskLabel="Shared link" />;
}
