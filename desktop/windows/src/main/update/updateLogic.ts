// Pure decision logic for the auto-updater, split out from the Electron glue in
// autoUpdate.ts so it can be unit-tested under node Vitest (which can't import
// `electron` / `electron-updater`). Mirrors the foregroundTargetLogic split.

export interface UpdateEnv {
  /** electron-toolkit `is.dev` — running under the Vite dev server. */
  isDev: boolean
  /** `app.isPackaged` — false for an unpacked/dev build. electron-updater only
   *  works against a packaged build (it reads the embedded app-update.yml). */
  isPackaged: boolean
  /** Bench runs (OMI_BENCH=1) must never reach out to GitHub. */
  isBench: boolean
}

/**
 * Whether the app should check GitHub Releases for updates this launch. We only
 * check from a real packaged build, never in dev or bench. Keeping this pure
 * makes the (otherwise untestable) Electron wiring trivially verifiable.
 */
export function shouldCheckForUpdates(env: UpdateEnv): boolean {
  if (env.isBench) return false
  if (env.isDev) return false
  if (!env.isPackaged) return false
  return true
}
