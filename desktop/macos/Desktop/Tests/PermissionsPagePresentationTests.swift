import XCTest

@testable import Omi_Computer

@MainActor
final class PermissionsPagePresentationTests: XCTestCase {
  func testSettledHeaderDropsTheWarningGlyphAndCapitalizesOmi() {
    XCTAssertEqual(PermissionsPageChrome.headerSymbol(allRequiredGranted: true), "checkmark.circle.fill")
    XCTAssertFalse(PermissionsPageChrome.headerSymbol(allRequiredGranted: true)?.contains("exclamationmark") == true)
    XCTAssertEqual(PermissionsPageChrome.headerTitle, "Permissions")
    XCTAssertEqual(
      PermissionsPageChrome.allGrantedMessage,
      "All permissions granted! Omi is ready to use.")
    XCTAssertTrue(PermissionsPageChrome.allGrantedMessage.contains("Omi"))
    XCTAssertFalse(PermissionsPageChrome.allGrantedMessage.contains("omi "))
  }

  func testMissingHeaderIsJustTheTitle() {
    XCTAssertNil(PermissionsPageChrome.headerSymbol(allRequiredGranted: false))
    XCTAssertEqual(PermissionsPageChrome.headerTitle, "Permissions")
  }

  func testSidebarUsesALock() {
    XCTAssertEqual(PermissionNavSymbol.outline, "lock")
    XCTAssertEqual(PermissionNavSymbol.filled, "lock.fill")
    XCTAssertEqual(SidebarNavItem.permissions.icon, PermissionNavSymbol.filled)
    XCTAssertEqual(ChatFirstMorePage.permissions.systemImage, PermissionNavSymbol.filled)
  }

  func testSettingsListOrderPlacesPermissionsWithAccessSettings() {
    XCTAssertEqual(
      SettingsSidebarRoutes.visibleSections,
      [
        .general,
        .account,
        .transcription,
        .rewind,
        .floatingBar,
        .notifications,
        .permissions,
        .shortcuts,
        .advanced,
        .referral,
        .about,
      ])
  }

  func testMissingGrantNoticeSitsBesideTheLockNotInsteadOfIt() {
    XCTAssertEqual(PermissionNavSymbol.missingNotice, "exclamationmark.triangle.fill")
    XCTAssertNotEqual(PermissionNavSymbol.outline, PermissionNavSymbol.missingNotice)
  }

  func testGrantedCapabilitiesDoNotStayAsActionCards() {
    XCTAssertFalse(PermissionsPageChrome.microphoneNeedsAction(granted: true))
    XCTAssertTrue(PermissionsPageChrome.microphoneNeedsAction(granted: false))

    XCTAssertFalse(PermissionsPageChrome.screenRecordingNeedsAction(granted: true, stale: false))
    XCTAssertTrue(PermissionsPageChrome.screenRecordingNeedsAction(granted: true, stale: true))
    XCTAssertTrue(PermissionsPageChrome.screenRecordingNeedsAction(granted: false, stale: false))

    XCTAssertFalse(PermissionsPageChrome.notificationsNeedAction(granted: true))
    XCTAssertTrue(PermissionsPageChrome.notificationsNeedAction(granted: false))
  }

  func testUnknownSystemAudioStaysActionableAfterRequiredGrants() {
    XCTAssertTrue(PermissionsPageChrome.systemAudioNeedsAction(status: .unknown))
    XCTAssertTrue(PermissionsPageChrome.systemAudioNeedsAction(status: .denied))
    XCTAssertFalse(PermissionsPageChrome.systemAudioNeedsAction(status: .granted))
    XCTAssertFalse(PermissionsPageChrome.systemAudioNeedsAction(status: .unsupported))
  }

  func testMissingStatusChipIsAlwaysNotGranted() {
    XCTAssertEqual(PermissionsPageChrome.statusChipText(granted: true), "Granted")
    XCTAssertEqual(PermissionsPageChrome.statusChipText(granted: false), "Not Granted")
    XCTAssertEqual(PermissionsPageChrome.missingStatusText, "Not Granted")
  }

  // MARK: - Accessibility

  /// The page must offer a row for every permission the app counts as required. These two sets
  /// diverged once: `AppState.missingPermissions` has counted Accessibility since before this
  /// page existed, but the page had no section for it, so the sidebar wore a warning triangle
  /// that no visible control could clear and "All permissions granted" was unreachable.
  func testPageActsOnEveryPermissionTheAppRequires() {
    let required: Set<String> = [
      "Microphone", "Screen Recording", "System Audio", "Notifications", "Accessibility",
    ]
    XCTAssertEqual(
      PermissionsPageChrome.requiredKinds, required,
      "a permission the app can report missing must have a row that can fix it")
    XCTAssertTrue(
      required.isSubset(of: PermissionsPageChrome.actionableKinds),
      "every required permission must be actionable on the page")
  }

  /// Bluetooth, Full Disk Access, and Automation are probed at every launch and were displayed
  /// nowhere, so a grant revoked after onboarding was invisible until the feature quietly failed.
  func testSupportingPermissionsAreShownButNotRequired() {
    let supporting: Set<String> = ["Bluetooth", "Full Disk Access", "Automation"]
    XCTAssertEqual(PermissionsPageChrome.supportingKinds, supporting)
    XCTAssertTrue(supporting.isSubset(of: PermissionsPageChrome.actionableKinds))
    XCTAssertTrue(
      PermissionsPageChrome.requiredKinds.isDisjoint(with: supporting),
      "a feature-scoped permission must not block the all-granted state or warn the sidebar")
  }

  func testSupportingPermissionsNeedActionOnlyWhenUngranted() {
    XCTAssertTrue(PermissionsPageChrome.bluetoothNeedsAction(granted: false))
    XCTAssertFalse(PermissionsPageChrome.bluetoothNeedsAction(granted: true))
    XCTAssertTrue(PermissionsPageChrome.fullDiskAccessNeedsAction(granted: false))
    XCTAssertFalse(PermissionsPageChrome.fullDiskAccessNeedsAction(granted: true))
    XCTAssertTrue(PermissionsPageChrome.automationNeedsAction(granted: false))
    XCTAssertFalse(PermissionsPageChrome.automationNeedsAction(granted: true))
  }

  func testAccessibilityNeedsActionWhenUngranted() {
    XCTAssertTrue(PermissionsPageChrome.accessibilityNeedsAction(granted: false, broken: false))
  }

  /// The state this machine was actually in: the toggle reads enabled, the AX calls fail. If a
  /// working grant and a stuck one look the same, the page tells the user to do the one thing
  /// that cannot help.
  func testAccessibilityNeedsActionWhenGrantedButBroken() {
    XCTAssertTrue(PermissionsPageChrome.accessibilityNeedsAction(granted: true, broken: true))
  }

  func testAccessibilitySettlesOnlyWhenGrantedAndWorking() {
    XCTAssertFalse(PermissionsPageChrome.accessibilityNeedsAction(granted: true, broken: false))
  }

  // MARK: - Notifications: notDetermined must never read as denied

  /// The exact bug: `isNotificationPermissionDenied()` used to return
  /// `hasCompletedOnboarding && !hasNotificationPermission`, which is true for
  /// BOTH `.notDetermined` and `.denied`. A user who was simply never asked then
  /// saw "previously denied, open System Settings" — a dead end, because macOS
  /// typically does not even list an app under System Settings > Notifications
  /// until it has called `requestAuthorization` once. Only a real `.denied`
  /// answer may read as denied.
  func testIsNotificationPermissionDeniedIsFalseForNotDeterminedAndTrueForDenied() {
    let appState = AppState()
    appState.hasCompletedOnboarding = true

    appState.notificationAuthorizationStatus = .notDetermined
    XCTAssertFalse(
      appState.isNotificationPermissionDenied(),
      "notDetermined (never asked) must not read as denied")

    appState.notificationAuthorizationStatus = .denied
    XCTAssertTrue(
      appState.isNotificationPermissionDenied(),
      "a real denied answer must still read as denied")

    appState.notificationAuthorizationStatus = .authorized
    XCTAssertFalse(appState.isNotificationPermissionDenied())
  }

  /// Before onboarding completes, a never-asked user must not be told they were
  /// denied either — the flag was never meant to fire ahead of onboarding.
  func testIsNotificationPermissionDeniedStaysFalseBeforeOnboardingCompletes() {
    let appState = AppState()
    appState.hasCompletedOnboarding = false
    appState.notificationAuthorizationStatus = .denied
    XCTAssertFalse(appState.isNotificationPermissionDenied())
  }
}
