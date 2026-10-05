import { requireNativeModule } from 'expo-modules-core'
import type { Route, RouteProvider } from './src/services/localBrainRouter'

// Present only when the native module is linked. Absent in Expo Go and in tests,
// so callers must handle null rather than assume it exists.
const native = requireNativeModule<any>('LocalBrain') as
  | {
      configure(prototypes: Record<string, string[]>, outOfDomain: string[]): Promise<{ ok: boolean }>
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
    }
  | null

export const isLocalBrainAvailable = native != null

/**
 * Builds a RouteProvider backed by the native router, or null when unavailable.
 *
 * `configure` must run before the first route: the prototype bank is supplied from
 * JS rather than baked into the asset, so the routing vocabulary stays reviewable
 * in TypeScript. That is why the banks cross the bridge on every call path rather
 * than being read natively once.
 */
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
