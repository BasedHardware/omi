import XCTest

@testable import Omi_Computer

final class UpdaterViewModelTests: XCTestCase {
  func testManualCheckIsUnavailableWhileBackgroundUpdateSessionIsInProgress() {
    XCTAssertFalse(
      UpdaterViewModel.allowsManualCheck(
        canCheckForUpdates: true,
        updateSessionInProgress: true
      )
    )
  }

  func testManualCheckRequiresSparkleToAllowChecking() {
    XCTAssertFalse(
      UpdaterViewModel.allowsManualCheck(
        canCheckForUpdates: false,
        updateSessionInProgress: false
      )
    )
  }

  func testManualCheckIsAvailableWhenNoSessionIsInProgress() {
    XCTAssertTrue(
      UpdaterViewModel.allowsManualCheck(
        canCheckForUpdates: true,
        updateSessionInProgress: false
      )
    )
  }
}
