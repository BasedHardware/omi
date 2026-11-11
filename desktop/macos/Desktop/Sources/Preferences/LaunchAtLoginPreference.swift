import Foundation

/// The policy half of launch-at-login: who decided, and what the default is.
///
/// `LaunchAtLoginManager` owns the system call; this type owns the user's
/// recorded intent and the one-shot default-on migration decision, so both are
/// testable without `SMAppService`. Rule: Omi launches at login unless the user
/// turned it off in Settings. A fresh install starts on; an existing install is
/// re-evaluated exactly once (V2) and enabled unless the decline marker exists.
enum LaunchAtLoginPreference {
  static let migrationV2Key = "didMigrateLaunchAtLoginV2"
  /// V1's key. Never read by the app any more; named so tests can pin that V2 does not share it.
  static let legacyMigrationV1Key = "didMigrateLaunchAtLoginV1"

  struct MigrationDecision: Equatable {
    let shouldRun: Bool
    let shouldEnable: Bool
    let reason: String
  }

  /// Fresh installs default to on. The onboarding seed reads this instead of
  /// the live `SMAppService` status, which is always "not registered" before
  /// the first registration.
  static func defaultForOnboarding(defaults: UserDefaults = .standard) -> Bool {
    !userDeclined(defaults: defaults)
  }

  /// `true` only if the user explicitly switched Launch at Login off in Settings.
  static func userDeclined(defaults: UserDefaults = .standard) -> Bool {
    defaults.object(forKey: DefaultsKey.launchAtLoginUserDeclined.rawValue) != nil
  }

  /// Called from the Settings toggle. Declining writes a presence marker;
  /// re-enabling removes it so the toggle stays authoritative in both directions.
  static func recordUserChoice(enabled: Bool, defaults: UserDefaults = .standard) {
    if enabled {
      defaults.removeObject(forKey: DefaultsKey.launchAtLoginUserDeclined.rawValue)
    } else {
      defaults.set(true, forKey: DefaultsKey.launchAtLoginUserDeclined.rawValue)
    }
  }

  /// Pure decision for the one-shot V2 migration at app launch.
  ///
  /// - Runs at most once per install (`migrationV2Key`).
  /// - Users still in onboarding are left to the onboarding seed.
  /// - A recorded decline wins; everyone else is enabled.
  static func migrationDecision(defaults: UserDefaults, hasCompletedOnboarding: Bool) -> MigrationDecision {
    if defaults.bool(forKey: migrationV2Key) {
      return MigrationDecision(shouldRun: false, shouldEnable: false, reason: "already migrated")
    }
    if !hasCompletedOnboarding {
      // Do not consume the one shot: the onboarding seed handles this user now, and the
      // next launch after completion re-checks nothing because the seed already applied.
      return MigrationDecision(shouldRun: false, shouldEnable: false, reason: "onboarding incomplete")
    }
    if userDeclined(defaults: defaults) {
      return MigrationDecision(shouldRun: true, shouldEnable: false, reason: "user declined in Settings")
    }
    return MigrationDecision(shouldRun: true, shouldEnable: true, reason: "default on")
  }

  static func markMigrationDone(defaults: UserDefaults) {
    defaults.set(true, forKey: migrationV2Key)
  }
}
