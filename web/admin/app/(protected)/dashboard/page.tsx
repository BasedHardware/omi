"use client";

// The analytics dashboard IS the Grafana "Omi TV" board, embedded full-bleed.
// Non-kiosk so Grafana's own Edit mode (drag, resize, remove, save) works
// right inside the page. Same origin in prod via the /grafana/* rewrite;
// NEXT_PUBLIC_GRAFANA_URL overrides for local dev. The previous chart grid
// lives on at /dashboard/classic.
const GRAFANA_URL =
  process.env.NEXT_PUBLIC_GRAFANA_URL ?? "/grafana/d/omi-tv/omi-tv?refresh=5m";

export default function AnalyticsPage() {
  return (
    <div className="-m-4 md:-m-6 h-[calc(100vh-3.5rem)]">
      <iframe
        src={GRAFANA_URL}
        title="Omi analytics (Grafana)"
        className="h-full w-full border-0"
        allow="fullscreen"
      />
    </div>
  );
}
