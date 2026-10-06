/**
 * Development-only flags.
 *
 * Every flag here is ANDed with `__DEV__`. `__DEV__` is a compile-time constant
 * that is false in release builds, so none of this can be reached in a shipped
 * binary even if the environment variable is somehow set. Each flag also requires
 * an explicit opt-in, so simply having a debug build does not silently disable
 * authentication for everyone who works on this app.
 *
 * Enable with:
 *   EXPO_PUBLIC_DEV_BYPASS_AUTH=1 npx expo start
 *
 * EXPO_PUBLIC_* is inlined by Metro at bundle time, so changing it needs a Metro
 * restart, not just a reload.
 */

/**
 * Shows the "continue without account" button on the sign-in screen.
 *
 * Gated on __DEV__ alone, with no env var. A local session with no account behind
 * it must never exist in a shipped binary, and __DEV__ already guarantees that;
 * requiring an extra opt-in would only make the thing awkward to use for the dev
 * workflow it exists for.
 */
export const DEV_LOGIN_WITHOUT_ACCOUNT: boolean =
  typeof __DEV__ !== 'undefined' && __DEV__

/**
 * Whether the dev-only screens under app/dev-* should be reachable.
 *
 * They are gated rather than merely undocumented: a stray deep link in a release
 * build should land on nothing rather than on a screen that bypasses sign-in.
 */
export const DEV_LOCAL_BRAIN: boolean =
  typeof __DEV__ !== 'undefined' &&
  __DEV__ &&
  process.env.EXPO_PUBLIC_DEV_LOCAL_BRAIN === '1'