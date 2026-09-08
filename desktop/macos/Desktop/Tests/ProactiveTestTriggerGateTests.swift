import XCTest

@testable import Omi_Computer

/// Guards issue #11943: the CLI test-notification observers
/// (`com.omi.test.notification` / `com.omi.test.insight`) were registered
/// unconditionally, so any local process could post a distributed notification and
/// have a shipped build deliver an arbitrary proactive notification and journal it
/// into the signed-in user's real backend chat.
final class ProactiveTestTriggerGateTests: XCTestCase {
  private func configuration(_ bundleIdentifier: String) -> AppBuild.Configuration {
    AppBuild.configuration(bundleIdentifier: bundleIdentifier, infoDictionary: [:])
  }

  func testShippedBundlesDoNotAllowCLITestTriggers() {
    // Both shipped identities. #11943 was observed on Omi Beta specifically: it received
    // every trigger aimed at a dev bundle and journaled 13 test notifications into a real
    // account, so beta must be asserted alongside stable rather than assumed to follow.
    for bundleIdentifier in AppBuild.productionFamilyBundleIdentifiers {
      XCTAssertFalse(
        configuration(bundleIdentifier).allowsLocalAutomation,
        "\(bundleIdentifier) must ignore CLI test triggers")
    }
  }

  func testExternalPreviewBundlesDoNotAllowCLITestTriggers() {
    // Preview builds ship outside the team and are non-production, so the broader
    // `isNonProduction` predicate would have left this hole open.
    let preview = configuration("com.omi.preview.p8b1f42a9")
    XCTAssertTrue(preview.isNonProduction, "preview shares the non-production namespace")
    XCTAssertFalse(preview.allowsLocalAutomation, "but must still ignore CLI test triggers")
  }

  func testLocalDevelopmentBundlesStillAllowCLITestTriggers() {
    // The gate must not break the workflow it exists to serve — `omi-*` named bundles are
    // how the notification delivery contract is exercised against a real running app.
    XCTAssertTrue(configuration(AppBuild.desktopDevBundleIdentifier).allowsLocalAutomation)
    XCTAssertTrue(configuration("com.omi.omi-fix-rewind").allowsLocalAutomation)
  }

  /// Returns nil when the source is correctly gated, or a failure reason when it is not.
  private func ungatedRegistrationReason(in source: String) -> String? {
    guard let range = source.range(of: "private func setupTestNotificationListeners() {") else {
      return "setupTestNotificationListeners was renamed — re-point this guard"
    }
    let body = source[range.upperBound...]
    guard let registration = body.range(of: "DistributedNotificationCenter") else {
      return "observer registration moved out of setupTestNotificationListeners"
    }
    guard
      body[..<registration.lowerBound].contains("guard AppBuild.allowsLocalAutomation else")
    else {
      return "observers registered without the AppBuild.allowsLocalAutomation gate"
    }
    return nil
  }

  /// Proves the static contract below actually discriminates. Without this, a scan that silently
  /// stopped matching would read as PASS forever — the failure mode that makes source-inspection
  /// guards untrustworthy. Fixtures are used so the real guard is never removed to test it.
  func testGateDetectorRejectsUngatedSource() {
    let ungated = """
      private func setupTestNotificationListeners() {
        let observers = [ProactiveTestNotificationObserver(name: name) { _ in }]
        for observer in observers { observer.register(in: DistributedNotificationCenter.default()) }
      }
      """
    XCTAssertEqual(
      ungatedRegistrationReason(in: ungated),
      "observers registered without the AppBuild.allowsLocalAutomation gate")

    let gated = """
      private func setupTestNotificationListeners() {
        guard AppBuild.allowsLocalAutomation else { return }
        let observers = [ProactiveTestNotificationObserver(name: name) { _ in }]
        for observer in observers { observer.register(in: DistributedNotificationCenter.default()) }
      }
      """
    XCTAssertNil(ungatedRegistrationReason(in: gated))
  }

  /// The defect was an absent guard in a private method on a MainActor plugin that cannot be
  /// instantiated headlessly, and AppBuild reads Bundle.main, so no behavioral seam observes the
  /// registration decision. The predicate tests above carry the behavioral half; this pins the
  /// guard's presence, and testGateDetectorRejectsUngatedSource proves the scan discriminates.
  func testRegistrationSiteKeepsTheGate() throws {
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources", isDirectory: true)
    // omi-test-quality: source-inspection -- static contract: pins the AppBuild.allowsLocalAutomation guard at an unobservable private registration site (issue #11943)
    let plugin = try String(
      contentsOf: sourcesRoot.appendingPathComponent(
        "ProactiveAssistants/ProactiveAssistantsPlugin.swift"),
      encoding: .utf8)

    XCTAssertNil(
      ungatedRegistrationReason(in: plugin),
      "CLI test observers must stay gated behind AppBuild.allowsLocalAutomation (issue #11943)")
  }
}
