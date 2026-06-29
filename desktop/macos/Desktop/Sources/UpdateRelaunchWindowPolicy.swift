import Foundation

struct UpdateRelaunchWindowPolicy {
  static let foregroundGraceInterval: TimeInterval = 30

  private static let pendingRelaunchKey = "sparkleUpdateRelaunchPending"
  private static let restoreMainWindowKey = "sparkleUpdateRelaunchRestoreMainWindow"

  static func shouldRestoreMainWindow(
    appIsActive: Bool,
    frontmostBundleMatches: Bool,
    mainWindowIsKey: Bool,
    lastMainWindowForegroundAt: Date?,
    now: Date = Date(),
    foregroundGraceInterval: TimeInterval = foregroundGraceInterval
  ) -> Bool {
    if appIsActive && frontmostBundleMatches && mainWindowIsKey {
      return true
    }

    guard let lastMainWindowForegroundAt else {
      return false
    }

    return now.timeIntervalSince(lastMainWindowForegroundAt) <= foregroundGraceInterval
  }

  static func markPendingRelaunch(restoreMainWindow: Bool, defaults: UserDefaults = .standard) {
    defaults.set(true, forKey: pendingRelaunchKey)
    defaults.set(restoreMainWindow, forKey: restoreMainWindowKey)
    defaults.synchronize()
  }

  static func consumePendingRelaunch(defaults: UserDefaults = .standard) -> Bool? {
    guard defaults.bool(forKey: pendingRelaunchKey) else {
      return nil
    }

    let restoreMainWindow = defaults.bool(forKey: restoreMainWindowKey)
    defaults.removeObject(forKey: pendingRelaunchKey)
    defaults.removeObject(forKey: restoreMainWindowKey)
    defaults.synchronize()
    return restoreMainWindow
  }
}
