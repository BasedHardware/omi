import XCTest

@testable import Omi_Computer

final class DesktopUpdateStatusPresentationTests: XCTestCase {
  func testIdleWhenNoSessionAndNoUpdate() {
    XCTAssertEqual(
      DesktopUpdateStatusPresentation.kind(
        sessionInProgress: false,
        updateAvailable: false,
        availableVersion: ""
      ),
      .idle
    )
  }

  func testCheckingWhileSessionInProgressWithoutKnownUpdate() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: true,
      updateAvailable: false,
      availableVersion: ""
    )
    XCTAssertEqual(kind, .checking)
    XCTAssertEqual(kind.title, "Checking for updates…")
    XCTAssertTrue(kind.showsProgress)
  }

  func testDownloadingWhenSessionAndUpdateAvailable() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: true,
      updateAvailable: true,
      availableVersion: "0.12.149"
    )
    XCTAssertEqual(kind, .downloading(version: "0.12.149"))
    XCTAssertEqual(kind.detail, "v0.12.149")
    XCTAssertEqual(kind.compactTitle, "Downloading v0.12.149…")
  }

  func testUpdateAvailableWithoutActiveSession() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: false,
      updateAvailable: true,
      availableVersion: "0.12.149"
    )
    XCTAssertEqual(kind, .updateAvailable(version: "0.12.149"))
    XCTAssertFalse(kind.showsProgress)
  }

  func testDeferredRecordingTakesPrecedence() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: true,
      updateAvailable: true,
      availableVersion: "0.12.149",
      restartImminent: true,
      deferredForRecording: true
    )
    XCTAssertEqual(kind, .deferredForRecording(version: "0.12.149"))
    XCTAssertEqual(kind.title, "Update ready — waiting for quiet moment")
  }

  func testRestartImminentTakesPrecedenceOverDownloading() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: true,
      updateAvailable: true,
      availableVersion: "0.12.149",
      restartImminent: true
    )
    XCTAssertEqual(kind, .restartImminent(version: "0.12.149"))
    XCTAssertEqual(kind.title, "Update ready — Omi will restart")
  }
}
