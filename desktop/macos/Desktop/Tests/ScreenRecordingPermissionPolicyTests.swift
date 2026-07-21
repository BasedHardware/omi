import AppKit
import XCTest

@testable import Omi_Computer

final class ScreenRecordingPermissionPolicyTests: XCTestCase {
  private func sourceFile(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }

  /// PERM-02 / BL-050: register the screen-recording TCC row while Omi is
  /// frontmost, then open Settings. The guided-grant helper must call
  /// requestAllScreenCapturePermissions() BEFORE openScreenRecordingPreferences(),
  /// and requestAll must activate before CGRequestScreenCaptureAccess(). A
  /// backgrounded request never creates the row (the Wave-11 failure).
  func testGuidedGrantRegistersBeforeOpeningSettings() throws {
    let src = try sourceFile("Sources/ScreenCaptureService.swift")
    guard let fn = src.range(of: "static func requestScreenRecordingAccessAndOpenSettings() {"),
      let end = src.range(of: "\n  }", range: fn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("requestScreenRecordingAccessAndOpenSettings must exist") }
    let body = String(src[fn.upperBound..<end])
    guard let reg = body.range(of: "requestAllScreenCapturePermissions()")?.lowerBound,
      let open = body.range(of: "openScreenRecordingPreferences()")?.lowerBound
    else { return XCTFail("helper must both register and open Settings") }
    XCTAssertLessThan(reg, open, "must register the TCC row before opening System Settings")

    guard let rfn = src.range(of: "static func requestAllScreenCapturePermissions() {"),
      let rend = src.range(of: "\n  }", range: rfn.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("requestAllScreenCapturePermissions must exist") }
    let rbody = String(src[rfn.upperBound..<rend])
    guard let act = rbody.range(of: "NSApp.activate()")?.lowerBound,
      let cg = rbody.range(of: "CGRequestScreenCaptureAccess()")?.lowerBound
    else { return XCTFail("requestAll must activate and request") }
    XCTAssertLessThan(act, cg, "NSApp.activate() must precede CGRequestScreenCaptureAccess()")
  }

  /// The permission buttons must use the register-first helper, not the old
  /// open-Settings-then-asyncAfter-register anti-pattern that backgrounded the
  /// app before registering.
  func testPermissionButtonsUseRegisterFirstHelper() throws {
    // Positive guard: every screen-recording grant surface routes through the
    // register-first helper (each of these files had an open-then-register path).
    for path in [
      "Sources/MainWindow/Pages/PermissionsPage.swift",
      "Sources/MainWindow/SidebarView.swift",
      "Sources/Rewind/UI/RewindPage.swift",
      "Sources/MainWindow/Pages/DashboardPage.swift",
      "Sources/OmiApp.swift",
      "Sources/MainWindow/Pages/Settings/Components/SettingsContentView+BillingHelpers.swift",
      "Sources/MainWindow/RewindOnlyView.swift",
    ] {
      XCTAssertTrue(
        try sourceFile(path).contains("requestScreenRecordingAccessAndOpenSettings()"),
        "\(path) must route its screen-recording grant through the register-first helper")
    }
    // Negative guard: the register-after-open-Settings anti-pattern is gone.
    for path in [
      "Sources/MainWindow/Pages/PermissionsPage.swift",
      "Sources/MainWindow/SidebarView.swift",
      "Sources/Rewind/UI/RewindPage.swift",
      "Sources/MainWindow/Pages/DashboardPage.swift",
    ] {
      let src = try sourceFile(path)
      XCTAssertNil(
        src.range(
          of:
            "openScreenRecordingPreferences\\([\\s\\S]{0,240}(requestAllScreenCapturePermissions|triggerScreenRecordingPermission)",
          options: .regularExpression),
        "\(path) still opens Settings before requesting screen-recording access")
    }
  }

  func testUiPermissionFollowsTccGrant() {
    XCTAssertTrue(ScreenRecordingPermissionPolicy.uiPermissionGranted(tccGranted: true))
    XCTAssertFalse(ScreenRecordingPermissionPolicy.uiPermissionGranted(tccGranted: false))
  }

  func testDeniedScreenRecordingAlwaysRoutesToSettings() {
    XCTAssertEqual(
      ScreenCaptureService.screenRecordingRequestDestination(hasPermissionNow: true),
      .alreadyGranted)
    XCTAssertEqual(
      ScreenCaptureService.screenRecordingRequestDestination(hasPermissionNow: false),
      .systemSettings)
  }

  @MainActor
  func testDragPayloadIsAFileURL() {
    let appURL = URL(fileURLWithPath: "/Applications/omi-screen-drag-test.app")
    let pasteboard = NSPasteboard(name: .init("omi-screen-recording-drag-test"))
    pasteboard.clearContents()

    XCTAssertTrue(
      pasteboard.writeObjects([AppBundleDragSourceNSView.pasteboardWriter(for: appURL)]))
    XCTAssertEqual(pasteboard.string(forType: .fileURL), appURL.absoluteString)
  }

  @MainActor
  func testDragSourceRendersIconBeforeInteraction() {
    let icon = NSImage(size: NSSize(width: 8, height: 8), flipped: false) { rect in
      NSColor.red.setFill()
      rect.fill()
      return true
    }
    let view = AppBundleDragSourceNSView(frame: NSRect(x: 0, y: 0, width: 32, height: 32))
    view.image = icon
    let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds)!
    view.cacheDisplay(in: view.bounds, to: bitmap)

    XCTAssertGreaterThan(bitmap.colorAt(x: 16, y: 16)?.alphaComponent ?? 0, 0.5)
  }

  @MainActor
  func testDragIconShrinksAsItEntersSystemSettings() {
    let settingsFrame = CGRect(x: 100, y: 100, width: 600, height: 500)

    XCTAssertEqual(
      AppBundleDragSourceNSView.dragIconSize(
        pointer: CGPoint(x: 80, y: 300), targetFrame: settingsFrame),
      AppBundleDragSourceNSView.fullDragIconSize)
    XCTAssertEqual(
      AppBundleDragSourceNSView.dragIconSize(
        pointer: CGPoint(x: 100, y: 300), targetFrame: settingsFrame),
      AppBundleDragSourceNSView.fullDragIconSize)
    XCTAssertEqual(
      AppBundleDragSourceNSView.dragIconSize(
        pointer: CGPoint(x: 140, y: 300), targetFrame: settingsFrame),
      AppBundleDragSourceNSView.compactDragIconSize)
  }

  @MainActor
  func testDragHelperSkipsFadeForReducedMotion() {
    XCTAssertEqual(CloudConnectorGuidanceOverlay.dragCardInitialAlpha(reduceMotion: false), 0)
    XCTAssertEqual(CloudConnectorGuidanceOverlay.dragCardInitialAlpha(reduceMotion: true), 1)
  }

  /// The drag card sits centered in the bottom quarter of the screen (below the
  /// Settings list, never covering the drop target), x-centered on the anchor.
  @MainActor
  func testDragCardSitsInBottomQuarterOfScreen() {
    let visible = CGRect(x: 0, y: 0, width: 1600, height: 1000)
    let card = CGSize(width: 180, height: 164)
    let anchor = CGRect(x: 900, y: 300, width: 600, height: 500)

    let frame = CloudConnectorGuidanceOverlay.dragCardFrame(
      anchor: anchor, cardSize: card, visibleFrame: visible)
    XCTAssertEqual(frame.midX, anchor.midX)
    XCTAssertLessThanOrEqual(frame.maxY, visible.minY + visible.height / 4)

    // No anchor → centered on the screen, still in the bottom quarter.
    let centered = CloudConnectorGuidanceOverlay.dragCardFrame(
      anchor: nil, cardSize: card, visibleFrame: visible)
    XCTAssertEqual(centered.midX, visible.midX)
    XCTAssertLessThanOrEqual(centered.maxY, visible.minY + visible.height / 4)
  }

  @MainActor
  func testDragCardExpandsForLongBundleDisplayNames() {
    XCTAssertEqual(
      CloudConnectorGuidanceOverlay.dragCardSize(appName: "Omi Dev"),
      CGSize(width: 180, height: 164))
    XCTAssertEqual(
      CloudConnectorGuidanceOverlay.dragCardSize(appName: "omi-tool-stall-reliability"),
      CGSize(width: 240, height: 180))
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

  /// Regression: the onboarding request tool reopened System Settings (and the
  /// FDA drag card) even when the permission was already granted. Opening must
  /// stay behind a granted check, like the notifications/automation cases.
  func testRequestToolOpensSettingsOnlyWhenDenied() throws {
    // omi-test-quality: source-inspection -- static contract: the tool's
    // NSWorkspace/System Settings side effects cannot be exercised hermetically.
    let src = try sourceFile("Sources/Providers/ChatToolExecutor.swift")
    for (caseStart, caseEnd, grantedGuard, pane) in [
      ("case \"screen_recording\":", "case \"microphone\":", "if !screenRecordingGranted {", "Privacy_ScreenCapture"),
      ("case \"full_disk_access\":", "default:", "if !checkFullDiskAccessDirectly() {", "Privacy_AllFiles"),
    ] {
      guard let start = src.range(of: caseStart)?.upperBound,
        let end = src.range(of: caseEnd, range: start..<src.endIndex)?.lowerBound
      else { return XCTFail("request tool must handle \(caseStart)") }
      let body = String(src[start..<end])
      guard let guardPos = body.range(of: grantedGuard)?.lowerBound,
        let openPos = body.range(of: pane)?.lowerBound
      else { return XCTFail("\(caseStart) must guard its \(pane) open behind \(grantedGuard)") }
      XCTAssertLessThan(
        guardPos, openPos,
        "\(caseStart): opening \(pane) must sit inside the not-granted branch")
    }
  }

  /// Regression: the onboarding "Reopen Omi" prompt looped forever because the
  /// offer was static step config with no memory of restarts. The offer must
  /// fire only for a grant that arrived during this process's lifetime.
  func testRelaunchOfferedOnlyForGrantsArrivingWhileRunning() {
    XCTAssertTrue(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: true, grantedAtLaunch: false),
      "granted while running → capture is dead until relaunch, offer the reopen")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: true, grantedAtLaunch: true),
      "already granted at launch (incl. right after a reopen) → never re-offer")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: false, grantedAtLaunch: false),
      "not granted → nothing to apply")
    XCTAssertFalse(
      ScreenRecordingPermissionPolicy.needsRelaunchToApply(
        grantedNow: false, grantedAtLaunch: true),
      "revoked while running → a relaunch can't help; the grant flow handles it")
  }

  func testScreenCaptureRestartsUseSharedRelaunchCommand() throws {
    let src = try sourceFile("Sources/ScreenCaptureService.swift")
    XCTAssertTrue(src.contains("static func screenCaptureRelaunchCommand(appPath: String) -> String"))
    XCTAssertTrue(src.contains("AppState.relaunchCommand("))

    guard let softRange = src.range(of: "static func softRecoveryAndRestart()"),
      let resetRange = src.range(of: "static func resetScreenCapturePermissionAndRestart()")
    else { return XCTFail("screen-capture restart helpers must exist") }
    let softSnippet = String(src[softRange.lowerBound...]).prefix(4200)
    let resetSnippet = String(src[resetRange.lowerBound...]).prefix(3000)

    XCTAssertTrue(softSnippet.contains("screenCaptureRelaunchCommand(appPath: bundleURL.path)"))
    XCTAssertTrue(resetSnippet.contains("screenCaptureRelaunchCommand(appPath: bundleURL.path)"))
    XCTAssertFalse(softSnippet.contains("sleep 0.5 && open"))
    XCTAssertFalse(resetSnippet.contains("sleep 0.5 && open"))
  }
}
