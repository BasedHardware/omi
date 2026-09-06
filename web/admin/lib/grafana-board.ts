export const GRAFANA_BOARD_UIDS: Record<string, string> = {
  macos: "omi-tv-macos",
  mobile: "omi-tv-mobile",
};

/** Same-origin Grafana path used by /dashboard and TV kiosk iframes. */
export function grafanaBoardPath(
  platform: string | null | undefined,
  kiosk = false
): string {
  const key = platform ?? "";
  const uid = Object.hasOwn(GRAFANA_BOARD_UIDS, key)
    ? GRAFANA_BOARD_UIDS[key]
    : "omi-tv";
  const qs = kiosk ? "refresh=5m&kiosk" : "refresh=5m";
  return `/grafana/d/${uid}/?${qs}`;
}

/**
 * Iframe src. `NEXT_PUBLIC_GRAFANA_URL` overrides the whole URL (local dev)
 * and ignores platform, matching /dashboard.
 */
export function grafanaBoardSrc(
  platform: string | null | undefined,
  kiosk = false
): string {
  const override = process.env.NEXT_PUBLIC_GRAFANA_URL ?? "";
  if (override) {
    if (!kiosk) return override;
    if (/(?:[?&])kiosk(?:&|=|$)/.test(override)) return override;
    return override.includes("?") ? `${override}&kiosk` : `${override}?kiosk`;
  }
  return grafanaBoardPath(platform, kiosk);
}
