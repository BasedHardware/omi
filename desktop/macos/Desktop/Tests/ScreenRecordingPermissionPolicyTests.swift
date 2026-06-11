import XCTest

@testable import Omi_Computer

final class ScreenRecordingPermissionPolicyTests: XCTestCase {
  func testUiPermissionFollowsTccGrant() {
    XCTAssertTrue(ScreenRecordingPermissionPolicy.uiPermissionGranted(tccGranted: true))
    XCTAssertFalse(ScreenRecordingPermissionPolicy.uiPermissionGranted(tccGranted: false))
  }

  func testCaptureKitFailureDoesNotOverrideGrantedTccPermission() {
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.shouldMarkCaptureKitBroken(tccGranted: true),
      "If System Settings/TCC says Screen Recording is granted, capture failures must not make the permission badge red"
    )
  }

  func testCaptureKitFailureDoesNotCreatePermissionFailureWhenTccIsDenied() {
    XCTAssertFalse(ScreenRecordingPermissionPolicy.shouldMarkCaptureKitBroken(tccGranted: false))
  }
}
