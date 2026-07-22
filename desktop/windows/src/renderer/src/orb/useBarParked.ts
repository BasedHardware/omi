import { useEffect, useState } from 'react'

/**
 * True while the floating-bar window is parked off-screen (main's park state).
 *
 * The bar is a persistent, always-on-top overlay window: after the first summon it
 * stays SHOWN and is merely moved off-screen to "hide", so Electron never marks it
 * `document.hidden` (window-occlusion tracking is macOS-only) and Chromium never
 * background-throttles it. A loop gated only on document visibility therefore keeps
 * running at display refresh rate forever once the bar has been summoned once
 * (perf-profile 2026-07-19, hotspot #2). Main is the only party that knows the real
 * parked state, so it pushes `bar:parked` on every park/unpark transition; the orb
 * ANDs this into its 0fps-hidden gate to actually stop the WebGL loop while parked.
 *
 * No-op outside the bar window: `bar:parked` is sent only to the bar renderer, so
 * every other orb mount (sidebar header, onboarding) keeps the default `false` and
 * is unaffected. `onParked` is optional-chained so a window without the bar preload
 * simply never subscribes.
 */
export function useBarParked(): boolean {
  const [parked, setParked] = useState(false)
  useEffect(() => window.omiBar?.onParked?.((p) => setParked(p)), [])
  return parked
}
