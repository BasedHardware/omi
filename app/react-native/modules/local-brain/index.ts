import { requireNativeModule } from 'expo-modules-core'
import type { Route, RouteProvider } from '../../src/services/localBrainRouter'

// Present only when the native module is linked. Absent in Expo Go and in tests,
// so callers must handle null rather than assume it exists.
interface LocalBrainNative {
  configure(
    prototypes: Record<string, string[]>,
    outOfDomain: string[]
  ): Promise<{ ok: boolean }>
  load(): Promise<{ ok: boolean; ready: boolean }>
  route(text: string): Promise<{
    route: Route
    margin: number
    declined: boolean
    negated: boolean
    runnerUp: string
    latencyMs: number
    reason: string
  }>
  isReady(): Promise<boolean>
  warmUp(): Promise<boolean>
}

// requireNativeModule throws when the module is absent, so probe first. This is
// what keeps the app rendering under Expo Go and in tests.
function probe(): LocalBrainNative | null {
  try {
    return requireNativeModule<LocalBrainNative>('LocalBrain')
  } catch {
    return null
  }
}

const native = probe()

export const isLocalBrainAvailable = native != null

/**
 * Builds a RouteProvider backed by the native router, or null when unavailable.
 *
 * `configure` must run before the first route: the prototype bank is supplied from
 * JS rather than baked into the asset, so the routing vocabulary stays reviewable
 * in TypeScript. That is why the banks cross the bridge on every call path rather
 * than being read natively once.
 */
/**
 * Loads the model without routing anything.
 *
 * The first route on an SM-A145F costs ~19.5 s against ~600 ms steady state, so
 * this exists to move that cost to a moment where nobody is waiting. Safe to call
 * repeatedly and safe to call with no router in hand: returns false rather than
 * throwing when the model is missing, leaving every route to decline to the
 * heuristic.
 */
export async function warmUp(
  prototypes: Record<Route, string[]>,
  outOfDomain: string[]
): Promise<boolean> {
  if (!native) return false
  try {
    // configure first: the router refuses to load without prototypes, and it is
    // right to. Configuring here rather than lazily inside route() is what lets the
    // load happen without pretending to route anything.
    await native.configure(prototypes, outOfDomain)
    await native.warmUp()
    return true
  } catch {
    return false
  }
}

export function createNativeRouter(
  prototypes: Record<Route, string[]>,
  outOfDomain: string[]
): RouteProvider | null {
  if (!native) return null
  let configured: Promise<unknown> | null = null
  return {
    async route(text: string) {
      configured ??= native.configure(prototypes, outOfDomain)
      await configured
      const r = await native.route(text)
      return { route: r.route, margin: r.margin, declined: r.declined }
    },
  }
}
