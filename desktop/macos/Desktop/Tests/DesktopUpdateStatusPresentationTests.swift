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

  func testCheckingOnlyWhenUserInitiatedSessionWithoutKnownUpdate() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: true,
      updateAvailable: false,
      availableVersion: "",
      userInitiatedCheck: true
    )
    XCTAssertEqual(kind, .checking)
    XCTAssertEqual(kind.title, "Checking for updates…")
    XCTAssertEqual(kind.checkActionTitle, "Checking…")
    XCTAssertTrue(kind.showsProgress)
  }

  func testBackgroundSessionAloneDoesNotShowCheckingChip() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: true,
      updateAvailable: false,
      availableVersion: "",
      userInitiatedCheck: false
    )
    XCTAssertEqual(kind, .idle)
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
    XCTAssertEqual(kind.checkActionTitle, "Downloading…")
  }

  func testUpdateAvailableWithoutActiveSession() {
    let kind = DesktopUpdateStatusPresentation.kind(
      sessionInProgress: false,
      updateAvailable: true,
      availableVersion: "0.12.149"
    )
    XCTAssertEqual(kind, .updateAvailable(version: "0.12.149"))
    XCTAssertFalse(kind.showsProgress)
    XCTAssertEqual(kind.checkActionTitle, "Check Now")
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
    XCTAssertEqual(kind.checkActionTitle, "Waiting…")
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
    XCTAssertEqual(kind.checkActionTitle, "Restarting…")
  }

  func testChatFirstAndSettingsHostTheSharedUpdateStatusSurfaces() throws {
    // Drift guard: chat-first top bar + Settings must keep hosting the shared
    // chip/card; the legacy sidebar no longer owns a private widget.
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources", isDirectory: true)

    func read(_ relative: String) throws -> String {
      try String(contentsOf: sourcesRoot.appendingPathComponent(relative), encoding: .utf8)
    }

    let presentation = try read("MainWindow/DesktopUpdateStatusPresentation.swift")
    XCTAssertTrue(presentation.contains("canManuallyCheckForUpdates"))
    XCTAssertFalse(presentation.contains("if updaterViewModel.canCheckForUpdates"))

    let topBar = try read("MainWindow/DesktopTopBar.swift")
    XCTAssertTrue(topBar.contains("DesktopUpdateStatusChip"))

    let settings = try read("MainWindow/Pages/Settings/Components/SettingsContentView+Controls.swift")
    XCTAssertTrue(settings.contains("DesktopUpdateStatusPresentation.kind"))
    XCTAssertTrue(settings.contains("checkActionTitle"))
  }
}
