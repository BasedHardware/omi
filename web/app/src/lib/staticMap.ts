import { getIdToken } from './firebase';

export interface MapPin {
  latitude: number;
  longitude: number;
}

/** Maximum pins `GET /v1/static-map` accepts after de-duplication. */
export const STATIC_MAP_MAX_PINS = 50;

const MIN_AXIS_PX = 64;
const MAX_AXIS_PX = 1280;
// Round requested sizes up to a coarse step so a resizing container reuses one
// server-cached render instead of requesting a new image per pixel.
const SIZE_STEP_PX = 40;

/**
 * Serializes pins exactly like the mobile app's `buildOmiStaticMapUrl`:
 * quantized to four decimals (~11m, the server's cache quantization),
 * de-duplicated after quantization, and capped at the backend limit.
 */
export function staticMapPinsParam(pins: readonly MapPin[]): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const pin of pins) {
    if (parts.length >= STATIC_MAP_MAX_PINS) break;
    const value = `${pin.latitude.toFixed(4)},${pin.longitude.toFixed(4)}`;
    if (seen.has(value)) continue;
    seen.add(value);
    parts.push(value);
  }
  return parts.join('|');
}

export function staticMapAxisPx(px: number): number {
  const stepped = Math.ceil(px / SIZE_STEP_PX) * SIZE_STEP_PX;
  return Math.min(MAX_AXIS_PX, Math.max(MIN_AXIS_PX, stepped));
}

export function staticMapPath(pinsParam: string, width: number, height: number): string {
  return `/v1/static-map?pins=${encodeURIComponent(
    pinsParam,
  )}&width=${width}&height=${height}`;
}

/**
 * Fetches a rendered preview through the authenticated same-origin proxy. An
 * `<img>` cannot send the Firebase token, so callers display the Blob through an
 * object URL. Resolves null on any failure (signed out, 4xx/5xx, network) so the
 * caller keeps its pin-dot fallback; the backend records the provider degrade.
 */
export async function fetchStaticMap(
  path: string,
  signal?: AbortSignal,
): Promise<Blob | null> {
  try {
    const token = await getIdToken();
    if (!token) return null;
    const response = await fetch(`/api/proxy${path}`, {
      headers: { Authorization: `Bearer ${token}`, 'X-App-Platform': 'web' },
      signal,
    });
    if (!response.ok) return null;
    return await response.blob();
  } catch {
    return null;
  }
}

export function googleMapsUrl(latitude: number, longitude: number): string {
  return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
}
