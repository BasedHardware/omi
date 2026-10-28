"use client";

import { lazy, Suspense, useEffect, useState } from "react";
import useSWR from "swr";
import { grafanaRenewalDelay } from "@/lib/grafana-renewal";
import { authenticatedFetcher, useAuthToken } from "@/hooks/useAuthToken";
import { useSearchParams } from "next/navigation";

// Flag-off and rollback use the existing authenticated native analytics page.
const ClassicDashboard = lazy(() => import("./classic/page"));

function GrafanaFrame() {
  const params = useSearchParams();
  const { token } = useAuthToken();
  const [retry, setRetry] = useState(0);
  const {
    data: embed,
    error,
    isLoading,
    mutate,
  } = useSWR(
    token ? ["/api/grafana/embed", token, retry] : null,
    ([url, auth]: [string, string, number]) =>
      authenticatedFetcher([url, auth]),
    {
      refreshInterval: (data) =>
        data?.enabled ? grafanaRenewalDelay(data.expiresAt) : 0,
      revalidateOnFocus: false,
      shouldRetryOnError: false,
    }
  );
  useEffect(() => {
    const resume = () => {
      if (
        document.visibilityState === "visible" &&
        embed?.enabled &&
        embed.expiresAt <= Date.now() + 60_000
      )
        void mutate();
    };
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [embed, mutate]);
  const tvParam = params?.get("tv") ?? null;
  const scale = tvParam
    ? Math.min(Math.max(parseFloat(tvParam) || 1, 0.25), 1)
    : 1;
  if (!embed && (isLoading || !token))
    return <p role="status">Loading dashboard…</p>;
  if (error) {
    // The Business board needs finance:read; a member without it gets the
    // classic analytics dashboard, which is scoped to analytics:read.
    if ((error as { status?: number }).status === 403) {
      return (
        <Suspense fallback={<p role="status">Loading analytics…</p>}>
          <ClassicDashboard />
        </Suspense>
      );
    }
    return (
      <div role="alert">
        <p>Dashboard login unavailable.</p>
        <button onClick={() => setRetry((value) => value + 1)}>
          Retry dashboard login
        </button>
        <a href="/dashboard/classic">Open analytics dashboard</a>
      </div>
    );
  }
  if (!embed?.enabled)
    return (
      <Suspense fallback={<p role="status">Loading analytics…</p>}>
        <ClassicDashboard />
      </Suspense>
    );
  const pct = `${(100 / scale).toFixed(4)}%`;

  return (
    <div className="-m-4 h-[calc(100vh-3.5rem)] overflow-hidden md:-m-6">
      {embed?.enabled && (
        <button
          className="absolute right-4 top-16 z-10 rounded bg-background px-2 py-1 text-xs"
          onClick={() => setRetry((value) => value + 1)}
        >
          Refresh dashboard login
        </button>
      )}
      <iframe
        src={embed.url}
        title="Omi analytics (Grafana)"
        referrerPolicy="no-referrer"
        className="border-0"
        allow="fullscreen"
        style={{
          width: pct,
          height: pct,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
      />
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense fallback={null}>
      <GrafanaFrame />
    </Suspense>
  );
}
