import XCTest

@testable import Omi_Computer

/// These features have a client half and a backend half, and they are scoped differently:
/// the backend rollout flags are per-deployment (`dev` only), while PostHog targets users.
/// The beta bundle is the one production-family identity pinned to the dev backend, so it is
/// the only one whose uploads have a consumer.
final class BetaDogfoodRolloutTests: XCTestCase {
  private func isEnabled(
    isNonProduction: Bool = false,
    isBeta: Bool = false,
    override: String? = nil,
    flag: Bool = false,
    kill: Bool = false
  ) -> Bool {
    BetaDogfoodRollout.isEnabled(
      isNonProduction: isNonProduction,
      isBetaProductionBundle: isBeta,
      localOverrideValue: override,
      isFlagEnabled: flag,
      isKillSwitchEnabled: kill)
  }

  func testBetaDogfoodsWithoutAnyPostHogConfiguration() {
    // The point of the change: enabling beta must not depend on a dashboard edit, because a
    // PostHog cohort cannot express "only the bundle that talks to the dev backend".
    XCTAssertTrue(isEnabled(isBeta: true))
  }

  func testBetaCanStillBeDisarmedWithoutShippingABuild() {
    XCTAssertFalse(isEnabled(isBeta: true, kill: true))
  }

  func testBetaIgnoresThePositiveStableFlag() {
    // A stable rollout must not be the thing that turns beta on or off.
    XCTAssertTrue(isEnabled(isBeta: true, flag: false))
    XCTAssertFalse(isEnabled(isBeta: true, flag: true, kill: true))
  }

  func testStableStaysDarkUntilItsOwnFlagIsTrue() {
    XCTAssertFalse(isEnabled())
    XCTAssertTrue(isEnabled(flag: true))
    // The beta kill switch must not reach stable.
    XCTAssertTrue(isEnabled(flag: true, kill: true))
  }

  func testDevelopmentBundlesStillRequireAnExplicitEnvironmentOverride() {
    XCTAssertFalse(isEnabled(isNonProduction: true))
    XCTAssertFalse(isEnabled(isNonProduction: true, flag: true))
    XCTAssertTrue(isEnabled(isNonProduction: true, override: "1"))
    XCTAssertFalse(isEnabled(isNonProduction: true, override: "0"))
  }

  func testEveryBetaDogfoodedFeatureSharesOneDecision() {
    // Meeting identity, on-device identity, and lossless screen sync all reach beta the same
    // way. If a future feature ships dark past this helper it will be invisible on beta, which
    // is the failure this asserts against: the names must stay paired with the kill switches.
    let features: [(String, String)] = [
      (SystemCalendarMeetingContextFeature.flagName, SystemCalendarMeetingContextFeature.killSwitchFlagName),
      (OnDeviceMeetingIdentityFeature.flagName, OnDeviceMeetingIdentityFeature.killSwitchFlagName),
      (ScreenActivityLosslessSyncFeature.flagName, ScreenActivityLosslessSyncFeature.killSwitchFlagName),
    ]
    for (flag, kill) in features {
      XCTAssertFalse(flag.isEmpty)
      XCTAssertEqual(kill, "\(flag)_kill", "a kill switch must be derivable from its flag name")
      XCTAssertTrue(isEnabled(isBeta: true), "beta dogfoods \(flag) by default")
      XCTAssertFalse(isEnabled(isBeta: true, kill: true), "\(flag) must stay disarmable on beta")
      XCTAssertFalse(isEnabled(), "\(flag) stays dark on stable")
    }
  }

  func testTheBetaBundleIsTheIdentityPinnedToTheDevBackend() {
    // Ties the rollout decision to the routing fact it depends on.
    XCTAssertTrue(
      DesktopBackendEnvironment.shouldForceDevelopmentServingEndpoints(
        bundleIdentifier: AppBuild.betaProductionBundleIdentifier))
    XCTAssertFalse(
      DesktopBackendEnvironment.shouldForceDevelopmentServingEndpoints(
        bundleIdentifier: AppBuild.productionBundleIdentifier))
    XCTAssertFalse(
      AppBuild.configuration(
        bundleIdentifier: AppBuild.betaProductionBundleIdentifier, infoDictionary: [:]
      ).isNonProduction)
  }
}
