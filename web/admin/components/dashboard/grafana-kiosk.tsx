"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import { grafanaRenewalDelay } from "@/lib/grafana-renewal";
import { grafanaBoardSrc } from "@/lib/grafana-board";

type TvEmbed = {
  enabled: boolean;
  legacy?: boolean;
  url?: string;
  expiresAt?: number;
};

/** POST the validated path token; the route re-validates server-side. */
async function tvEmbedFetcher([url, token]: [string, string]): Promise<TvEmbed> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
    cache: "no-store",
  });
  if (!response.ok) throw new Error("TV embed unavailable");
  return response.json();
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
  const [retry, setRetry] = useState(0);
  const {
    data: embed,
    error,
    isLoading,
    mutate,
  } = useSWR(["/api/grafana/tv-embed", token, retry], tvEmbedFetcher, {
    refreshInterval: (data) =>
      data?.enabled ? grafanaRenewalDelay(data.expiresAt ?? 0) : 0,
    revalidateOnFocus: false,
    shouldRetryOnError: false,
  });
  // A failed renewal must not strand an unattended TV on a dead iframe:
  // shouldRetryOnError:false leaves SWR's polling stopped while an error is
  // cached, so re-arm bounded automatic retries until a renewal succeeds.
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setRetry((value) => value + 1), 15_000);
    return () => clearTimeout(timer);
  }, [error, retry]);
  useEffect(() => {
    const resume = () => {
      if (
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
  }, [embed, mutate]);

  // Flag-off while legacy anonymous board still exists: keep it working.
  if (embed && !embed.enabled && embed.legacy) {
    return (
      <Suspense fallback={<div className="h-screen w-screen bg-black" />}>
        <LegacyKioskFrame />
      </Suspense>
    );
  }
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

function LegacyKioskFrame() {
  const params = useSearchParams();
  return (
    <KioskFrame src={grafanaBoardSrc(params?.get("platform") ?? null, true)} />
  );
}

export function GrafanaKiosk({ token }: { token: string }) {
  return (
    <Suspense fallback={<div className="h-screen w-screen bg-black" />}>
      <TvEmbedFrame token={token} />
    </Suspense>
  );
}
