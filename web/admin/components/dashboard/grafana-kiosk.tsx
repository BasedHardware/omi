"use client";

import { Suspense, useEffect } from "react";
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

  if (embed?.enabled && embed.url)
    return <KioskFrame src={embed.url} />;
  // Flag-off while legacy anonymous board still exists: keep it working.
  if (embed && !embed.enabled && embed.legacy) {
    return (
      <Suspense fallback={<div className="h-screen w-screen bg-black" />}>
        <LegacyKioskFrame />
      </Suspense>
    );
  }
  // Legacy closed or kiosk enrollment unavailable: honest native notice
  // instead of framing Grafana's login/denial page.
  if (error || (!isLoading && embed && !embed.enabled)) {
    return (
      <main className="flex h-screen w-screen items-center justify-center bg-neutral-950 px-6 text-center text-neutral-200">
        <div>
          <h1 className="text-xl font-semibold">TV dashboard unavailable</h1>
          <p className="mt-2 text-sm text-neutral-400">
            Ask an admin to enable the private TV dashboard or open
            /dashboard on a signed-in admin device.
          </p>
        </div>
      </main>
    );
  }
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
