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
}
