"use client";

import { Suspense, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { grafanaRenewalDelay } from "@/lib/grafana-renewal";

type TvEmbed = {
  enabled: boolean;
  url?: string;
  expiresAt?: number;
};

/** POST the validated path token; the route re-validates server-side. */
async function tvEmbedFetcher([url, token]: [
  string,
  string
]): Promise<TvEmbed> {
  const controller = new AbortController();
  // A stalled route (e.g. Firestore lookup hanging) must surface as an
  // error so renewal retry logic engages; a bare fetch would never settle.
  const timer = setTimeout(() => controller.abort(), 30_000);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      const error = new Error("TV embed unavailable") as Error & {
        status?: number;
      };
      error.status = response.status;
      throw error;
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function KioskFrame({ src }: { src: string }) {
  const params = useSearchParams();
  const tvParam = params?.get("tv") ?? null;
  const scale = tvParam
    ? Math.min(Math.max(parseFloat(tvParam) || 1, 0.25), 1)
    : 1;
  const pct = `${(100 / scale).toFixed(4)}%`;

  return (
    <div className="h-screen w-screen overflow-hidden bg-black">
      <iframe
        src={src}
        title="Omi TV"
        className="border-0"
        referrerPolicy="no-referrer"
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

function TvEmbedFrame({ token }: { token: string }) {
  const retryAttempt = useRef(0);
  const {
    data: embed,
    error,
    isLoading,
    mutate,
  } = useSWR(["/api/grafana/tv-embed", token], tvEmbedFetcher, {
    refreshInterval: (data) =>
      data?.enabled ? grafanaRenewalDelay(data.expiresAt ?? 0) : 0,
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  // A failed renewal must not strand an unattended TV on a dead iframe:
  // shouldRetryOnError:false leaves SWR's polling stopped while an error is
  // cached. Revalidate the SAME key with exponential backoff so no new
  // cache entries accumulate, and stop once the failure is permanent (the
  // link is revoked/expired; a new token requires a new URL anyway).
  useEffect(() => {
    if (!error) return;
    // 400/403 are permanent for this URL (invalid/revoked/expired link);
    // only transient failures (503, network) keep retrying.
    if (
      error.status >= 400 &&
      error.status < 500 &&
      ![408, 429].includes(error.status)
    )
      return;
    const capped = Math.min(retryAttempt.current, 5);
    const delay = Math.min(15_000 * 2 ** capped, 8 * 60_000);
    const timer = setTimeout(() => {
      retryAttempt.current = capped + 1;
      void mutate();
    }, delay);
    return () => clearTimeout(timer);
  }, [error, mutate]);
  useEffect(() => {
    // A successful fetch clears the backoff counter for the next renewal.
    if (!error && embed) retryAttempt.current = 0;
  }, [embed, error]);
  useEffect(() => {
    const resume = () => {
      if (
        !error &&
        document.visibilityState === "visible" &&
        embed?.enabled &&
        (embed.expiresAt ?? 0) <= Date.now() + 60_000
      ) {
        void mutate();
      }
    };
    window.addEventListener("focus", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      window.removeEventListener("focus", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [embed, mutate, error]);

  // Renewal failure shows the honest notice immediately — a stale embed must
  // not keep framing a dead JWT — and the bounded retry effect above
  // re-arms renewal so an unattended TV self-heals.
  if (error || (!isLoading && embed && !embed.enabled)) {
    return (
      <main className="flex h-screen w-screen items-center justify-center bg-neutral-950 px-6 text-center text-neutral-200">
        <div>
          <h1 className="text-xl font-semibold">TV dashboard unavailable</h1>
          <p className="mt-2 text-sm text-neutral-400">
            Retrying automatically. Ask an admin to check the private TV
            dashboard or open /dashboard on a signed-in admin device.
          </p>
        </div>
      </main>
    );
  }
  if (embed?.enabled && embed.url) return <KioskFrame src={embed.url} />;
  return <div className="h-screen w-screen bg-black" />;
}

export function GrafanaKiosk({ token }: { token: string }) {
  return (
    <Suspense fallback={<div className="h-screen w-screen bg-black" />}>
      <TvEmbedFrame token={token} />
    </Suspense>
  );
}
