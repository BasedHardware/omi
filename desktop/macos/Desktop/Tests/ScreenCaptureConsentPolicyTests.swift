import ScreenCaptureKit
import XCTest

@testable import Omi_Computer

/// The consent-re-prompt defect: with the Screen Recording grant intact, macOS
/// periodically re-confirms consent for app-built content filters, and while that
/// dialog is pending every capture fails with "The user declined TCCs…". Collapsing
/// that error into a generic `.failed` fed the 3 s retry loop that re-armed the dialog
/// (observed three re-prompts in ten minutes). These tests pin the two contracts that
/// fix it: the error is classified, and the classified error is terminal outside the
/// special system modes.
final class ScreenCaptureConsentPolicyTests: XCTestCase {
  private func sourceFile(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent().deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }

  // MARK: - Error classification

  func testUserDeclinedSCStreamErrorClassifiesAsPermissionDeclined() {
    let error = NSError(
      domain: SCStreamError.errorDomain,
      code: SCStreamError.userDeclined.rawValue,
      userInfo: nil
    )
    XCTAssertEqual(ScreenCaptureService.classifyCaptureError(error), .permissionDeclined)
  }

  /// The live-machine failure carried the complaint in the message; the substring
  /// fallback must catch it even under an unexpected code, because a missed decline
  /// silently reverts to the retry loop.
  func testDeclinedTCCMessageClassifiesAsPermissionDeclinedRegardlessOfCode() {
    let result = ScreenCaptureService.classifyCaptureError(
      domain: "com.apple.CoreGraphics",
      code: -1,
      description: "The user declined TCCs for application, window, display capture"
    )
    XCTAssertEqual(result, .permissionDeclined)
  }

  func testOtherSCStreamErrorsStayGenericFailures() {
    let error = NSError(
      domain: SCStreamError.errorDomain,
      code: SCStreamError.attemptToStopStreamState.rawValue,
      userInfo: [NSLocalizedDescriptionKey: "The stream is already stopped"]
    )
    XCTAssertEqual(ScreenCaptureService.classifyCaptureError(error), .other)
  }

  func testUnrelatedErrorClassifiesAsOther() {
    let error = NSError(
      domain: NSCocoaErrorDomain, code: 999,
      userInfo: [NSLocalizedDescriptionKey: "connection interrupted"])
    XCTAssertEqual(ScreenCaptureService.classifyCaptureError(error), .other)
  }

  // MARK: - Declined-capture action policy

  /// Exposé / Mission Control produce the same error transiently while they own the
  /// screen; that must stay a wait, never a terminal stop.
  func testSpecialSystemModeWaitsInsteadOfStopping() {
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: true, hasNotifiedThisSession: false),
      .waitForSpecialModeToEnd
    )
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: true, hasNotifiedThisSession: true),
      .waitForSpecialModeToEnd
    )
  }

  func testDeclineOutsideSpecialModeIsTerminalAndNotifiesOnce() {
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: false, hasNotifiedThisSession: false),
      .stopAndNotify(shouldNotify: true)
    )
    XCTAssertEqual(
      ScreenCaptureConsentPolicy.actionForDeclinedCapture(
        isInSpecialSystemMode: false, hasNotifiedThisSession: true),
      .stopAndNotify(shouldNotify: false)
    )
  }

  // MARK: - The retry loops must use the classified capture API

  /// The recovery poll (5 s) and background poll (60 s) were the amplifiers that
  /// re-armed the consent dialog: both probed with `captureActiveWindowAsync`, which
  /// returns `Data?` and erases the decline. Pin them to the classified API and to an
  /// explicit `.permissionDeclined` exit so a refactor cannot silently reintroduce the
  /// unclassified probe.
  func testRecoveryLoopsUseClassifiedCaptureAndExitOnDecline() throws {
    let src = try sourceFile("Sources/ProactiveAssistants/ProactiveAssistantsPlugin.swift")

    for fn in ["private func attemptRecovery() async {", "private func backgroundPollAttempt() async {"] {
      guard let start = src.range(of: fn),
        let end = src.range(of: "\n  }", range: start.upperBound..<src.endIndex)?.lowerBound
      else { return XCTFail("\(fn) must exist") }
      let body = String(src[start.upperBound..<end])
      XCTAssertTrue(
        body.contains("captureActiveWindowCGImage()"),
        "\(fn) must probe with the classified capture API")
      XCTAssertFalse(
        body.contains("captureActiveWindowAsync()"),
        "\(fn) must not use the unclassified Data? probe — it erases declined consent")
      XCTAssertTrue(
        body.contains("case .permissionDeclined:") && body.contains("handleCaptureConsentDeclined()"),
        "\(fn) must exit through the terminal consent handler on a decline")
    }
  }

  /// The capture tick itself must route a decline to the terminal handler, not the
  /// engine-failure counter (5 consecutive failures of which re-enter the retry loop).
  func testCaptureTickRoutesDeclineToTerminalHandler() throws {
    let src = try sourceFile("Sources/ProactiveAssistants/ProactiveAssistantsPlugin.swift")
    guard let start = src.range(of: "private func captureFrame() async {"),
      let end = src.range(of: "\n  }", range: start.upperBound..<src.endIndex)?.lowerBound
    else { return XCTFail("captureFrame must exist") }
    let body = String(src[start.upperBound..<end])
    XCTAssertTrue(
      body.contains("case .permissionDeclined:"),
      "captureFrame must handle the classified decline distinctly")
    XCTAssertTrue(
      body.contains("handleCaptureConsentDeclined()"),
      "captureFrame must route declines to the terminal consent handler")
  }
}
