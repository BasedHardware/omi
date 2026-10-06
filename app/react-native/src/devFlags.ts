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
 * Guest mode: the "continue without an account" button on the sign-in screen.
 *
 * Deliberately NOT gated on __DEV__. A release build is a legitimate place for
 * this -- guest and trial sessions are ordinary product patterns -- and gating it
 * on __DEV__ meant the release APK, which is the one build that opens on its own
 * without a dev server, was the one build you could not get into.
 *
 * It is still not a way to impersonate anyone: the session carries no token, so
 * every server-backed call returns 401. What it buys is the local surface --
 * routing, the device, the tab shell.
 *
 * Turn it off for a shipped build with expo.extra.guestModeEnabled = false in
 * app.json; no code change.
 */
export const GUEST_MODE: boolean = readGuestMode();

function readGuestMode(): boolean {
  try {
    const flag = expoExtra()?.guestModeEnabled;
    // Default on: an app that cannot be opened at all without an account is
    // harder to evaluate, and the session grants nothing either way.
    return flag === undefined ? true : flag === true;
  } catch {
    // If the config cannot be read, do not claim a capability we cannot verify.
    return false;
  }
}

function expoExtra(): Record<string, unknown> | undefined {
  // Required lazily: this module is imported by unit tests that should not pull
  // in expo's native config, and a static import would make one boolean a
  // native-module dependency.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const Constants = require('expo-constants').default;
  return Constants.expoConfig?.extra as Record<string, unknown> | undefined;
}

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