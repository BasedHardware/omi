"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

// The analytics dashboard IS the Grafana "Omi TV" board, embedded full-bleed.
// Non-kiosk so Grafana's own Edit mode (drag, resize, remove, save) works
// right inside the page. Same origin in prod via the /grafana/* rewrite;
// NEXT_PUBLIC_GRAFANA_URL overrides for local dev. The previous chart grid
// lives on at /dashboard/classic.
//
// TV mode: /dashboard?tv=0.55 scales the embed down so big-screen browsers
// (Fire TV Silk renders very zoomed-in) fit the whole board, and switches
// Grafana to kiosk chrome.
//
// Platform boards: /dashboard?platform=macos|mobile opens that platform's
// board directly instead of the All-platforms one.
const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_URL ?? "";
const BOARD_UIDS: Record<string, string> = {
  macos: "omi-tv-macos",
  mobile: "omi-tv-mobile",
};

export function boardUrl(platform: string | null): string {
  if (GRAFANA_URL) return GRAFANA_URL;
  const uid = BOARD_UIDS[platform ?? ""] ?? "omi-tv";
  return `/grafana/d/${uid}/?refresh=5m`;
}

function GrafanaFrame() {
  const params = useSearchParams();
  const tvParam = params?.get("tv") ?? null;
  const base = boardUrl(params?.get("platform") ?? null);
  const scale = tvParam ? Math.min(Math.max(parseFloat(tvParam) || 1, 0.25), 1) : 1;
  const src = tvParam ? `${base}&kiosk` : base;
  const pct = `${(100 / scale).toFixed(4)}%`;

  return (
    <div className="-m-4 md:-m-6 h-[calc(100vh-3.5rem)] overflow-hidden">
      <iframe
        src={src}
        title="Omi analytics (Grafana)"
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
