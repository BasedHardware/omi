/** Background state persistence.
 *
 *  When the phone goes to the background the Even Hub host migrates the plugin
 *  into a headless WebView: it snapshots JS state with `window.__getStateSnapshot()`,
 *  reloads the same URL in the headless view, and replays the snapshot through
 *  `window.__restoreState(json)`. A plugin that registers nothing gets `'{}'`
 *  back and restarts from its initial state every time the phone is unlocked.
 *
 *  `@evenrealities/even_hub_sdk@0.0.12` documents `setBackgroundState` /
 *  `onBackgroundRestore` but does not actually export them — the symbols are
 *  absent from both `dist/index.d.ts` and `dist/index.js`, and 0.0.12 is the
 *  latest published version. This module implements the same two functions
 *  against the host's documented window hooks, so call sites read exactly as
 *  they will once the SDK ships them and the import is a one-line swap.
 */

type Exporter = () => Record<string, unknown>
type Restorer = (saved: Record<string, unknown>) => void

const exporters = new Map<string, Exporter>()
const restorers = new Map<string, Restorer>()

type StateHost = {
  __getStateSnapshot?: () => string
  __restoreState?: (snapshot: string) => void
}

/** Register a snapshot producer for `key`. Must return plain JSON — no class
 *  instances, Maps, Sets or Dates, since the value round-trips through
 *  `JSON.stringify`. */
export function setBackgroundState(key: string, exporter: Exporter): void {
  exporters.set(key, exporter)
  install()
}

/** Register the matching restorer for `key`. Runs in the freshly loaded
 *  WebView, before the plugin has drawn anything. */
export function onBackgroundRestore(key: string, restorer: Restorer): void {
  restorers.set(key, restorer)
  install()
}

let installed = false

function install(): void {
  if (installed || typeof window === 'undefined') return
  installed = true
  const host = window as unknown as StateHost

  host.__getStateSnapshot = () => {
    const snapshot: Record<string, unknown> = {}
    for (const [key, exporter] of exporters) {
      try {
        snapshot[key] = exporter()
      } catch (error) {
        // One broken exporter must not cost the other keys their snapshot.
        console.error(`[state] exporter "${key}" threw:`, error)
      }
    }
    return JSON.stringify(snapshot)
  }

  host.__restoreState = (raw: string) => {
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch (error) {
      console.error('[state] snapshot is not valid JSON:', error)
      return
    }
    if (typeof parsed !== 'object' || parsed === null) return
    const snapshot = parsed as Record<string, unknown>

    for (const [key, restorer] of restorers) {
      const saved = snapshot[key]
      if (typeof saved !== 'object' || saved === null) continue
      try {
        restorer(saved as Record<string, unknown>)
        console.log(`[state] restored "${key}"`)
      } catch (error) {
        console.error(`[state] restorer "${key}" threw:`, error)
      }
    }
  }
}
