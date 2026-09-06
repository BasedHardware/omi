import XCTest

@testable import Omi_Computer

/// Launch at login is on unless the user turned it off in Settings.
///
/// Fresh installs used to seed the onboarding value from the live `SMAppService`
/// status, which is "not registered" for every new install, so every new user
/// finished onboarding with auto-start off and nothing could bring them back the
/// next day. The V1 migration could not tell a user's decline from "never set".
/// These tests pin the policy that replaced both.
final class LaunchAtLoginPreferenceTests: XCTestCase {
  private let suiteName = "LaunchAtLoginPreferenceTests.\(UUID().uuidString)"
  private var defaults: UserDefaults { UserDefaults(suiteName: suiteName) ?? .standard }

  override func tearDown() {
    defaults.removePersistentDomain(forName: suiteName)
    super.tearDown()
  }

  func testFreshInstallDefaultsOn() {
    XCTAssertTrue(LaunchAtLoginPreference.defaultForOnboarding(defaults: defaults))
    XCTAssertFalse(LaunchAtLoginPreference.userDeclined(defaults: defaults))
  }

  func testDecliningInSettingsIsRememberedAndReEnablingClearsIt() {
    LaunchAtLoginPreference.recordUserChoice(enabled: false, defaults: defaults)
    XCTAssertTrue(LaunchAtLoginPreference.userDeclined(defaults: defaults))
    XCTAssertFalse(LaunchAtLoginPreference.defaultForOnboarding(defaults: defaults))

    LaunchAtLoginPreference.recordUserChoice(enabled: true, defaults: defaults)
    XCTAssertFalse(LaunchAtLoginPreference.userDeclined(defaults: defaults))
    XCTAssertNil(
      defaults.object(forKey: DefaultsKey.launchAtLoginUserDeclined.rawValue),
      "Re-enabling must remove the marker, never write false")
  }

  func testMigrationEnablesExistingUserWhoNeverDeclined() {
    let decision = LaunchAtLoginPreference.migrationDecision(defaults: defaults, hasCompletedOnboarding: true)
    XCTAssertTrue(decision.shouldRun)
    XCTAssertTrue(decision.shouldEnable)
  }

  func testMigrationRespectsExplicitDecline() {
    LaunchAtLoginPreference.recordUserChoice(enabled: false, defaults: defaults)
    let decision = LaunchAtLoginPreference.migrationDecision(defaults: defaults, hasCompletedOnboarding: true)
    XCTAssertTrue(decision.shouldRun, "The one shot is consumed even when nothing changes")
    XCTAssertFalse(decision.shouldEnable)
  }

  func testMigrationLeavesOnboardingUsersToTheSeedWithoutConsumingTheShot() {
    let decision = LaunchAtLoginPreference.migrationDecision(defaults: defaults, hasCompletedOnboarding: false)
    XCTAssertFalse(decision.shouldRun)
    XCTAssertFalse(defaults.bool(forKey: LaunchAtLoginPreference.migrationV2Key))
  }

  func testMigrationRunsExactlyOnce() {
    let first = LaunchAtLoginPreference.migrationDecision(defaults: defaults, hasCompletedOnboarding: true)
    XCTAssertTrue(first.shouldRun)
    LaunchAtLoginPreference.markMigrationDone(defaults: defaults)
    let second = LaunchAtLoginPreference.migrationDecision(defaults: defaults, hasCompletedOnboarding: true)
    XCTAssertFalse(second.shouldRun)
    XCTAssertFalse(second.shouldEnable)
  }

  func testV2KeyIsDistinctFromV1SoTheInstallBaseIsReEvaluated() {
    // V1 already ran for everyone under the old semantics; a V2 that shared its key would never run.
    defaults.set(true, forKey: LaunchAtLoginPreference.legacyMigrationV1Key)
    let decision = LaunchAtLoginPreference.migrationDecision(defaults: defaults, hasCompletedOnboarding: true)
    XCTAssertTrue(decision.shouldRun)
    XCTAssertTrue(decision.shouldEnable)
  }
}
