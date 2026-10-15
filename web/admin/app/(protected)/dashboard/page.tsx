"use client";

import { Suspense, useEffect, useState } from "react";
import useSWR from "swr";
import { grafanaRenewalDelay } from "@/lib/grafana-renewal";
import { authenticatedFetcher, useAuthToken } from "@/hooks/useAuthToken";
import { useSearchParams } from "next/navigation";
import { grafanaBoardSrc } from "@/lib/grafana-board";

// Production switches to the private monitor.omi.me board only after the
// server-side rollout flag is enabled. Legacy TV share links retain their path.
// Renew URL login before expiry and on tab resume; upstream stats stay cached.
export function boardUrl(platform: string | null): string {
  return grafanaBoardSrc(platform, false);
}

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
  const kiosk = Boolean(tvParam);
  const base = grafanaBoardSrc(params?.get("platform") ?? null, kiosk);
  const scale = tvParam
    ? Math.min(Math.max(parseFloat(tvParam) || 1, 0.25), 1)
    : 1;
  const src = embed?.enabled ? embed.url : base;
  if (!embed && (isLoading || !token))
    return <p role="status">Loading dashboard…</p>;
  if (error)
    return (
      <div role="alert">
        <p>Dashboard login unavailable.</p>
        <button onClick={() => setRetry((value) => value + 1)}>
          Retry dashboard login
        </button>
      </div>
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
        src={src}
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
