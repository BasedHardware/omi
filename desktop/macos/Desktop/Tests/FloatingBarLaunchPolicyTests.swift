import XCTest

@testable import Omi_Computer

final class FloatingBarLaunchPolicyTests: XCTestCase {
  func testExplicitUserActionRevealsSnoozedFloatingBar() {
    XCTAssertTrue(
      FloatingBarPresentationPolicy.shouldPresent(
        request: .explicitUserAction,
        isSnoozed: true
      )
    )
  }

  func testBackgroundPresentationRemainsSuppressedWhileSnoozed() {
    XCTAssertFalse(
      FloatingBarPresentationPolicy.shouldPresent(
        request: .background,
        isSnoozed: true
      )
    )
  }

  func testBackgroundPresentationIsAllowedWhenNotSnoozed() {
    XCTAssertTrue(
      FloatingBarPresentationPolicy.shouldPresent(
        request: .background,
        isSnoozed: false
      )
    )
  }

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
    let floatingBarLaunchSection = try extractSection(
      from: source,
      startingAt: "// Set up floating control bar.",
      endingBefore: "// Set up push-to-talk voice input")

    XCTAssertTrue(
      floatingBarLaunchSection.contains("FloatingControlBarManager.shared.setup("),
      "DesktopHomeView must create the floating bar window before applying launch presentation.")
    XCTAssertTrue(
      floatingBarLaunchSection.contains(
        "FloatingControlBarManager.shared.presentForLaunch(context: .normalSignedInDesktop)"),
      "Normal DesktopHomeView launch must route through the normal signed-in floating-bar policy.")
    XCTAssertFalse(
      floatingBarLaunchSection.contains("showDeferredUntilFirstPushToTalk()"),
      "Deferred reveal hides the notch until PTT and must not be used for normal signed-in launch.")
    XCTAssertFalse(
      floatingBarLaunchSection.contains(".show()"),
      "DesktopHomeView must not bypass the launch policy with an ad-hoc immediate show call.")
    XCTAssertFalse(
      floatingBarLaunchSection.contains(".showTemporarily()"),
      "DesktopHomeView must not use temporary visibility for normal signed-in launch.")
  }

  private func sourceFile(_ relativePath: String) throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent(relativePath)
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func extractSection(from source: String, startingAt startMarker: String, endingBefore endMarker: String)
    throws -> String
  {
    guard let start = source.range(of: startMarker) else {
      XCTFail("Missing expected section start marker: \(startMarker)")
      return ""
    }
    guard let end = source.range(of: endMarker, range: start.upperBound..<source.endIndex) else {
      XCTFail("Missing expected section end marker: \(endMarker)")
      return ""
    }
    return String(source[start.lowerBound..<end.lowerBound])
  }
}
