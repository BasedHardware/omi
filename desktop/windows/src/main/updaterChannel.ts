// Pure mapping between the persisted "receive beta updates" opt-in and
// electron-updater's GitHub-provider prerelease lever. Kept in its own module —
// with NO electron / electron-updater imports — so the channel-selection logic is
// unit-testable in isolation (updater.ts itself can't load under vitest).
//
// Why `allowPrerelease` and not a semver channel: our Windows beta pipeline
// publishes betas as GitHub *prereleases* carrying plain patch semver (e.g.
// 1.0.5, no `-beta` suffix); "beta-ness" is the GitHub prerelease FLAG. The
// GitHubProvider serves those only when `allowPrerelease === true`; when false it
// reads GitHub's /releases/latest, which excludes prereleases. So the boolean
// opt-in maps straight onto `allowPrerelease` — the Windows analogue of Mac's
// additive Sparkle "beta" channel (UpdaterViewModel.allowedChannels).

/** The `autoUpdater.allowPrerelease` value for a given beta opt-in. */
export function betaOptInToAllowPrerelease(optIn: boolean): boolean {
  return optIn === true
}

/** Decide how the updater should react to a settings write. `onAppSettingsChanged`
 *  fires for EVERY app-settings write (hotkey rebinds, toggles, …), so only act
 *  when the beta opt-in actually moves the prerelease lever. `changed` gates both
 *  reassigning `allowPrerelease` and kicking an immediate re-check (so opting in
 *  surfaces a newer beta without waiting for the periodic timer). */
export function resolveBetaChannelChange(
  currentAllowPrerelease: boolean,
  nextOptIn: boolean
): { allowPrerelease: boolean; changed: boolean } {
  const allowPrerelease = betaOptInToAllowPrerelease(nextOptIn)
  return { allowPrerelease, changed: allowPrerelease !== currentAllowPrerelease }
}
