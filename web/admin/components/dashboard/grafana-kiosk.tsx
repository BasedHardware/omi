"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { grafanaBoardSrc } from "@/lib/grafana-board";

function GrafanaKioskFrame() {
  const params = useSearchParams();
  const tvParam = params?.get("tv") ?? null;
  const base = grafanaBoardSrc(params?.get("platform") ?? null, true);
  const scale = tvParam
    ? Math.min(Math.max(parseFloat(tvParam) || 1, 0.25), 1)
    : 1;
  const pct = `${(100 / scale).toFixed(4)}%`;

  return (
    <div className="h-screen w-screen overflow-hidden bg-black">
      <iframe
        src={base}
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

export function GrafanaKiosk() {
  return (
    <Suspense fallback={<div className="h-screen w-screen bg-black" />}>
      <GrafanaKioskFrame />
    </Suspense>
  );
}
