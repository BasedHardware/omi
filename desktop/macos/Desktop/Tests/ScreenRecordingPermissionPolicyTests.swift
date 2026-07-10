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
          of: "openScreenRecordingPreferences\\([\\s\\S]{0,240}(requestAllScreenCapturePermissions|triggerScreenRecordingPermission)",
          options: .regularExpression),
        "\(path) still opens Settings before requesting screen-recording access")
    }
  }

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
