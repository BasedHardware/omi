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

  func testOnboardingDemoPreservesFloatingBarPreference() {
    XCTAssertNil(FloatingBarPreferenceMutation.preserve.persistedEnabledValue)
  }

  func testUserVisibilityActionsStillUpdateFloatingBarPreference() {
    XCTAssertEqual(FloatingBarPreferenceMutation.setEnabled(true).persistedEnabledValue, true)
    XCTAssertEqual(FloatingBarPreferenceMutation.setEnabled(false).persistedEnabledValue, false)
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

  func testSpaceChangeRestoresOnlyAnEnabledPresentedBar() {
    XCTAssertTrue(
      FloatingBarDurableVisibilityPolicy.shouldRestoreWhenAppKitOrderedOut(
        isEnabled: true,
        isSnoozed: false,
        hasBeenPresentedThisSession: true))
    XCTAssertFalse(
      FloatingBarDurableVisibilityPolicy.shouldRestoreWhenAppKitOrderedOut(
        isEnabled: false,
        isSnoozed: false,
        hasBeenPresentedThisSession: true),
      "a settings-hidden bar must stay hidden across Space switches")
    XCTAssertFalse(
      FloatingBarDurableVisibilityPolicy.shouldRestoreWhenAppKitOrderedOut(
        isEnabled: true,
        isSnoozed: true,
        hasBeenPresentedThisSession: true),
      "a snoozed bar must stay hidden across Space switches")
    XCTAssertFalse(
      FloatingBarDurableVisibilityPolicy.shouldRestoreWhenAppKitOrderedOut(
        isEnabled: true,
        isSnoozed: false,
        hasBeenPresentedThisSession: false),
      "deferred-until-PTT launch must not promote the notch on a Space switch")
  }

  func testOnboardingDemoTeardownRestoresOnlyTheUsersDurableBar() {
    XCTAssertTrue(
      FloatingBarDurableVisibilityPolicy.shouldRestoreAfterOnboardingDemo(
        isEnabled: true,
        isSnoozed: false))
    XCTAssertFalse(
      FloatingBarDurableVisibilityPolicy.shouldRestoreAfterOnboardingDemo(
        isEnabled: false,
        isSnoozed: false),
      "demo teardown must not persist or reveal a disabled bar")
    XCTAssertFalse(
      FloatingBarDurableVisibilityPolicy.shouldRestoreAfterOnboardingDemo(
        isEnabled: true,
        isSnoozed: true))
  }

  func testRecenteringPrefersTheBarScreenOverTheKeyWindow() {
    XCTAssertEqual(
      FloatingBarPlacementScreenPolicy.screenForRecentering(
        barScreen: "laptop",
        cursorScreen: "studio",
        mainScreen: "studio",
        firstScreen: "studio"),
      "laptop",
      "an already-placed bar must not jump to the shell's display")
    XCTAssertEqual(
      FloatingBarPlacementScreenPolicy.screenForRecentering(
        barScreen: Optional<String>.none,
        cursorScreen: "studio",
        mainScreen: "laptop",
        firstScreen: "laptop"),
      "studio")
    XCTAssertNil(
      FloatingBarPlacementScreenPolicy.screenForRecentering(
        barScreen: Optional<String>.none,
        cursorScreen: Optional<String>.none,
        mainScreen: Optional<String>.none,
        firstScreen: Optional<String>.none))
  }

  func testIslandModeHoldsWhileAVisibleBarHasNoScreenYet() {
    XCTAssertTrue(
      FloatingBarPlacementScreenPolicy.shouldHoldIslandModeWhileScreenIsReassigning(
        isVisible: true,
        barScreenMissing: true))
    XCTAssertFalse(
      FloatingBarPlacementScreenPolicy.shouldHoldIslandModeWhileScreenIsReassigning(
        isVisible: false,
        barScreenMissing: true),
      "init still has to pick a mode before the panel is on a screen")
    XCTAssertFalse(
      FloatingBarPlacementScreenPolicy.shouldHoldIslandModeWhileScreenIsReassigning(
        isVisible: true,
        barScreenMissing: false))
  }

  func testSpaceChangeReconcilesFrameWhenIslandModeFlips() {
    XCTAssertTrue(
      FloatingBarPlacementScreenPolicy.shouldReconcileFrameAfterSpaceChange(
        isVisible: true,
        showingAIConversation: false,
        islandModeChanged: true,
        frameChanged: false,
        barScreenMissing: false),
      "flipping to pill without a resize leaves chrome inside the camera housing")
    XCTAssertFalse(
      FloatingBarPlacementScreenPolicy.shouldReconcileFrameAfterSpaceChange(
        isVisible: true,
        showingAIConversation: false,
        islandModeChanged: true,
        frameChanged: true,
        barScreenMissing: true),
      "do not guess a display while NSWindow.screen is still nil")
    XCTAssertFalse(
      FloatingBarPlacementScreenPolicy.shouldReconcileFrameAfterSpaceChange(
        isVisible: true,
        showingAIConversation: true,
        islandModeChanged: true,
        frameChanged: true,
        barScreenMissing: false),
      "an open chat owns its size")
  }

  func testVisibleBarDoesNotGuessAScreenWhileAppKitIsReassigning() {
    XCTAssertTrue(
      FloatingBarPlacementScreenPolicy.shouldSkipVisibleBarLayoutUntilScreenReturns(
        isVisible: true,
        barScreenMissing: true),
      "windowDidChangeScreen must wait for NSWindow.screen")
    XCTAssertFalse(
      FloatingBarPlacementScreenPolicy.shouldSkipVisibleBarLayoutUntilScreenReturns(
        isVisible: false,
        barScreenMissing: true),
      "initial placement may still choose a screen before the panel is visible")
    XCTAssertFalse(
      FloatingBarPlacementScreenPolicy.shouldSkipVisibleBarLayoutUntilScreenReturns(
        isVisible: true,
        barScreenMissing: false))
  }

  func testCancelledRetractWhileStillVisibleRestoresFullRevealProgress() {
    XCTAssertTrue(
      FloatingBarNotchRevealPolicy.shouldRestoreProgressAfterCancelledRetract(
        windowStillVisible: true,
        retractStillInFlight: false,
        revealStillInFlight: false))
    XCTAssertFalse(
      FloatingBarNotchRevealPolicy.shouldRestoreProgressAfterCancelledRetract(
        windowStillVisible: true,
        retractStillInFlight: true,
        revealStillInFlight: false),
      "a replacement retract still owns the collapsed scale")
    XCTAssertFalse(
      FloatingBarNotchRevealPolicy.shouldRestoreProgressAfterCancelledRetract(
        windowStillVisible: true,
        retractStillInFlight: false,
        revealStillInFlight: true),
      "a replacement reveal still owns the grow-in scale")
    XCTAssertFalse(
      FloatingBarNotchRevealPolicy.shouldRestoreProgressAfterCancelledRetract(
        windowStillVisible: false,
        retractStillInFlight: false,
        revealStillInFlight: false),
      "an ordered-out panel does not need a visible-scale restore")
  }

  func testDesktopHomeLaunchUsesNormalPolicyAndDoesNotCallDeferredRevealDirectly() throws {
    let source = try sourceFile("AccountCutover/DesktopHomeSignedInStartup.swift")
    let floatingBarLaunchSection = try extractSection(
      from: source,
      startingAt: "FloatingControlBarManager.shared.setup(",
      endingBefore: "if let barState = FloatingControlBarManager.shared.barState")

    XCTAssertTrue(
      floatingBarLaunchSection.contains("FloatingControlBarManager.shared.setup("),
      "Signed-in startup must create the floating bar window before applying launch presentation.")
    XCTAssertTrue(
      floatingBarLaunchSection.contains(
        "FloatingControlBarManager.shared.presentForLaunch(context: .normalSignedInDesktop)"),
      "Normal signed-in launch must route through the normal floating-bar policy.")
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
