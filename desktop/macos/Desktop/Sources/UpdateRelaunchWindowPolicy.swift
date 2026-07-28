import Foundation

struct UpdateInstallAttempt: Codable, Equatable {
  let id: String
  let sourceVersion: String
  let sourceBuild: String
  let targetVersion: String
  let targetBuild: String
  let channel: String
  let startedAt: Date

  var analyticsProperties: [String: Any] {
    [
      "update_attempt_id": id,
      "source_app_version": sourceVersion,
      "source_app_build": sourceBuild,
      "target_version": targetVersion,
      "target_build": targetBuild,
      "update_channel": channel,
      "update_started_at": ISO8601DateFormatter().string(from: startedAt),
    ]
  }
}

struct PendingUpdateRelaunch: Codable, Equatable {
  let restoreMainWindow: Bool
  let attempt: UpdateInstallAttempt?
}

struct UpdateRelaunchWindowPolicy {
  static let foregroundGraceInterval: TimeInterval = 30

  private static let pendingRelaunchKey = "sparkleUpdateRelaunchPending"
  private static let restoreMainWindowKey = "sparkleUpdateRelaunchRestoreMainWindow"
  private static let pendingRelaunchPayloadKey = "sparkleUpdateRelaunchPayload"

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

  static func markPendingRelaunch(
    restoreMainWindow: Bool,
    sourceVersion: String,
    sourceBuild: String,
    targetVersion: String,
    targetBuild: String,
    channel: String,
    attemptID: String = UUID().uuidString,
    startedAt: Date = Date(),
    defaults: UserDefaults = .standard
  ) -> UpdateInstallAttempt {
    let attempt = UpdateInstallAttempt(
      id: attemptID,
      sourceVersion: sourceVersion,
      sourceBuild: sourceBuild,
      targetVersion: targetVersion,
      targetBuild: targetBuild,
      channel: channel,
      startedAt: startedAt
    )
    let payload = PendingUpdateRelaunch(restoreMainWindow: restoreMainWindow, attempt: attempt)
    if let encoded = try? JSONEncoder().encode(payload) {
      defaults.set(encoded, forKey: pendingRelaunchPayloadKey)
    }
    defaults.set(true, forKey: pendingRelaunchKey)
    defaults.set(restoreMainWindow, forKey: restoreMainWindowKey)
    defaults.synchronize()
    return attempt
  }

  static func consumePendingRelaunch(defaults: UserDefaults = .standard) -> PendingUpdateRelaunch? {
    guard defaults.bool(forKey: pendingRelaunchKey) else {
      return nil
    }

    let payload =
      defaults.data(forKey: pendingRelaunchPayloadKey)
      .flatMap { try? JSONDecoder().decode(PendingUpdateRelaunch.self, from: $0) }
      ?? PendingUpdateRelaunch(
        restoreMainWindow: defaults.bool(forKey: restoreMainWindowKey),
        attempt: nil
      )
    defaults.removeObject(forKey: pendingRelaunchKey)
    defaults.removeObject(forKey: restoreMainWindowKey)
    defaults.removeObject(forKey: pendingRelaunchPayloadKey)
    defaults.synchronize()
    return payload
  }
}
