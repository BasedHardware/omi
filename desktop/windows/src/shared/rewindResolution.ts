// Capture-resolution presets for Rewind. Shared by the main-process settings
// sanitizer, the renderer capture host (getUserMedia + canvas downscale), and the
// Settings UI, so the offered options and the clamping stay in one place.
//
// `maxEdge` caps the LONGEST edge of a captured frame. getUserMedia fits the
// desktop stream within a maxEdge×maxEdge box preserving aspect ratio, so the
// longest edge never exceeds it regardless of monitor orientation; the canvas
// downscale enforces the same bound. Lower = cheaper (less decode + smaller OCR
// input + smaller stored JPEGs); higher = sharper small text.

export type CaptureResolution = { label: string; maxEdge: number; hint: string }

export const CAPTURE_RESOLUTIONS: readonly CaptureResolution[] = [
  { label: 'Low', maxEdge: 960, hint: 'lightest — 960px' },
  { label: 'Balanced', maxEdge: 1280, hint: 'default — 1280px' },
  { label: 'High', maxEdge: 1920, hint: 'sharpest — 1920px' }
]

export const DEFAULT_CAPTURE_MAX_EDGE = 1280

/**
 * Coerce an untrusted persisted value to one of the offered presets. Snaps to the
 * nearest preset (rather than clamping to an arbitrary number) so the Settings
 * picker always reflects the stored value. Falls back to the default for
 * non-numbers / non-positive input.
 */
export function clampCaptureMaxEdge(raw: unknown): number {
  if (typeof raw !== 'number' || !Number.isFinite(raw) || raw <= 0) return DEFAULT_CAPTURE_MAX_EDGE
  const allowed = CAPTURE_RESOLUTIONS.map((r) => r.maxEdge)
  return allowed.reduce((best, e) => (Math.abs(e - raw) < Math.abs(best - raw) ? e : best), allowed[0])
}
