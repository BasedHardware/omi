import XCTest

@testable import Omi_Computer

final class ScreenCaptureTargetPolicyTests: XCTestCase {
  func testLoginAndScreenSaverWaitWithoutRecordingFailure() {
    XCTAssertTrue(ScreenCaptureTargetPolicy.shouldWaitForUserWindow(appName: "loginwindow"))
    XCTAssertTrue(ScreenCaptureTargetPolicy.shouldWaitForUserWindow(appName: "ScreenSaverEngine"))
  }

  func testUserAppsAndUnknownTargetsRemainEligibleForCapture() {
    XCTAssertFalse(ScreenCaptureTargetPolicy.shouldWaitForUserWindow(appName: "Finder"))
    XCTAssertFalse(ScreenCaptureTargetPolicy.shouldWaitForUserWindow(appName: nil))
  }
}
