import XCTest
@testable import Omi_Computer

final class FloatingBarLaunchPolicyTests: XCTestCase {
  func testNormalSignedInLaunchShowsEnabledFloatingBarEvenOnNotchedDisplays() {
    XCTAssertEqual(
      FloatingBarLaunchPolicy.presentation(
        isEnabled: true,
        context: .normalSignedInDesktop,
        displayHasNotch: true),
      .showImmediately)
  }

  func testNormalSignedInLaunchShowsEnabledFloatingBarOnNonNotchedDisplays() {
    XCTAssertEqual(
      FloatingBarLaunchPolicy.presentation(
        isEnabled: true,
        context: .normalSignedInDesktop,
        displayHasNotch: false),
      .showImmediately)
  }

  func testDisabledFloatingBarStaysHiddenForEveryLaunchContext() {
    let contexts: [FloatingBarLaunchContext] = [
      .normalSignedInDesktop,
      .onboardingOrDemo,
      .explicitMinimalMode,
    ]

    for context in contexts {
      XCTAssertEqual(
        FloatingBarLaunchPolicy.presentation(
          isEnabled: false,
          context: context,
          displayHasNotch: true),
        .hidden)
    }
  }

  func testDeferredRevealIsOnlyForExplicitOptInContextsOnNotchedDisplays() {
    XCTAssertEqual(
      FloatingBarLaunchPolicy.presentation(
        isEnabled: true,
        context: .onboardingOrDemo,
        displayHasNotch: true),
      .deferUntilFirstPushToTalk)

    XCTAssertEqual(
      FloatingBarLaunchPolicy.presentation(
        isEnabled: true,
        context: .explicitMinimalMode,
        displayHasNotch: true),
      .deferUntilFirstPushToTalk)
  }

  func testDeferredRevealContextsFallBackToImmediateShowWithoutNotch() {
    let deferredContexts: [FloatingBarLaunchContext] = [
      .onboardingOrDemo,
      .explicitMinimalMode,
    ]

    for context in deferredContexts {
      XCTAssertEqual(
        FloatingBarLaunchPolicy.presentation(
          isEnabled: true,
          context: context,
          displayHasNotch: false),
        .showImmediately)
    }
  }

  func testDesktopHomeLaunchUsesNormalPolicyAndDoesNotCallDeferredRevealDirectly() throws {
    let source = try sourceFile("MainWindow/DesktopHomeView.swift")

    XCTAssertTrue(
      source.contains("context: .normalSignedInDesktop"),
      "Normal DesktopHomeView launch must route through the normal signed-in floating-bar policy.")
    XCTAssertTrue(
      source.contains("FloatingControlBarManager.shared.presentForLaunch(context: .normalSignedInDesktop)"),
      "DesktopHomeView must use the explicit normal-launch policy instead of ad-hoc show/defer calls.")
    XCTAssertFalse(
      source.contains("showInitial()"),
      "showInitial()/deferred reveal hides the notch until PTT and must not be used for normal signed-in launch.")
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
