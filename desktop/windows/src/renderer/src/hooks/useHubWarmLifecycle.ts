import { useEffect } from 'react'

/** The warm-hub opt-out contract (the `pttHubEnabled` kill-switch).
 *
 *  Eagerly warms the hub ONLY for a signed-in user with the flag on; in every other
 *  case it tears the socket down. Warming is what makes `hub.isAvailable()` true, so
 *  WITHOUT this the driver's `selectPttRoute` always sees an unavailable hub and
 *  every press falls straight to the cascade (the hub is dead). Signing out or
 *  flipping the pref off drops a live socket with no restart. Kept as a standalone
 *  hook so the contract is unit-testable against a fake hub.
 *
 *  The mint the warm path runs is `__sessionPreserving`, so a dead-session 401 while
 *  warming refreshes+retries once but never forces the user to the sign-in screen. */
export function useHubWarmLifecycle(
  hub: { warm: () => void; teardown: () => void },
  gate: { ready: boolean; signedIn: boolean; hubEnabled: boolean }
): void {
  const { ready, signedIn, hubEnabled } = gate
  useEffect(() => {
    if (ready && signedIn && hubEnabled) hub.warm()
    else hub.teardown()
  }, [ready, signedIn, hubEnabled, hub])
}
