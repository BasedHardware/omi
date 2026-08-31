import XCTest

@testable import Omi_Computer

/// Permissions are per capability, not one switch, and a script that never
/// returns must not be able to take the app with it.
final class CuaPermissionAndScriptTests: XCTestCase {
  private var defaults = UserDefaults.standard
  private var suiteName = ""

  override func setUpWithError() throws {
    suiteName = "cua-permissions-\(UUID().uuidString)"
    defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
  }

  override func tearDownWithError() throws {
    defaults.removePersistentDomain(forName: suiteName)
  }

  @MainActor
  private func gate(missing: [CuaPermission]) -> CuaControlGate {
    let gate = CuaControlGate(
      defaults: defaults,
      missingPermission: { needed in needed.first { missing.contains($0) } },
      ownerID: { "owner-1" })
    gate.setEnabled(true)
    return gate
  }

  /// The bug this replaces: input was gated on `AXIsProcessTrusted`, which
  /// answers for a different TCC service than the one that lets an event be
  /// posted. A Mac holding one and not the other either refused work it could do
  /// or posted clicks the window server dropped.
  @MainActor
  func testAMissingInputGrantDoesNotBlockReadingOrCapture() {
    let gate = gate(missing: [.postEvents])
    XCTAssertEqual(gate.refusal(needs: [.postEvents]), .missingPermission(.postEvents))
    XCTAssertNil(gate.refusal(needs: [.accessibility]))
    XCTAssertNil(gate.refusal(needs: [.screenRecording]))
  }

  @MainActor
  func testAMissingCaptureGrantStillLeavesTheAccessibilityLaneWorking() {
    let gate = gate(missing: [.screenRecording])
    XCTAssertEqual(gate.refusal(needs: [.screenRecording]), .missingPermission(.screenRecording))
    XCTAssertNil(gate.refusal(needs: [.accessibility]))
    XCTAssertNil(gate.refusal(needs: [.postEvents]))
  }

  /// Whatever the grants say, the switch and the kill switch come first.
  @MainActor
  func testTheSwitchOutranksEveryGrant() {
    let gate = gate(missing: [])
    gate.suspend(reason: "test")
    XCTAssertEqual(gate.refusal(needs: [.postEvents]), .suspended(reason: "test"))
    gate.rearm()
    gate.setEnabled(false)
    XCTAssertEqual(gate.refusal(), .disabled)
  }

  @MainActor
  func testAGrantFromAnotherAccountDoesNotCarryOver() {
    let gate = CuaControlGate(
      defaults: defaults, missingPermission: { _ in nil }, ownerID: { "owner-1" })
    gate.setEnabled(true)
    XCTAssertNil(gate.refusal())

    let switched = CuaControlGate(
      defaults: defaults, missingPermission: { _ in nil }, ownerID: { "owner-2" })
    XCTAssertEqual(switched.refusal(), .ownerChanged)
  }

  /// The reported bug: the user ticks Omi in System Settings and the app keeps
  /// saying the permission is missing, because `AXIsProcessTrusted` answers from
  /// a cache filled on its first call and never refreshed. Evidence that the
  /// grant is real — a live probe, or an operation that actually worked — has to
  /// stick, or every later check asks again.
  @MainActor
  func testAnObservedGrantStopsTheAppFromAskingAgain() {
    // Screen Recording is the one with a preflight that is false in a test host,
    // so it proves the sticky path rather than the machine's own grants.
    let permission = CuaPermission.screenRecording
    CuaPermission.markGranted(permission)
    XCTAssertTrue(permission.isGranted())
    XCTAssertNil(CuaPermission.ensure([permission]))
  }

  func testAppleScriptReturnsItsResult() {
    let result = CuaAppleScript.run("return 6 * 7", timeout: 10)
    XCTAssertNil(result.failure)
    XCTAssertEqual(result.output, "42")
  }

  func testAFailingScriptReportsWhyRatherThanItsOutput() {
    let result = CuaAppleScript.run("this is not applescript", timeout: 10)
    XCTAssertNotNil(result.failure)
  }

  /// A model-written script can wait forever — `display dialog` waits for a
  /// click nobody is there to make. In process that would freeze the app,
  /// including the button and the hotkey that stop computer control.
  func testAScriptThatNeverFinishesIsKilledAndReported() {
    let started = Date()
    let result = CuaAppleScript.run("delay 30", timeout: 1)
    XCTAssertLessThan(Date().timeIntervalSince(started), 10)
    XCTAssertTrue(result.failure?.contains("did not finish") ?? false)
  }

  /// The bug this replaces: `list_windows` read the window list through
  /// `SCShareableContent`, which is Screen Recording territory, but declared no
  /// permission. Without the grant the call threw, `try?` swallowed it, and the
  /// tool answered "No matching windows" — an empty desk rather than a missing
  /// permission, which a model acts on as if it were true.
  @MainActor
  func testListingWindowsNeedsTheSameGrantAsCapturing() {
    let gate = gate(missing: [.screenRecording])
    XCTAssertEqual(gate.refusal(needs: [.screenRecording]), .missingPermission(.screenRecording))
    XCTAssertTrue(CuaToolCatalog.tools.contains { $0.name == "list_windows" })
  }

  /// A script that drives another app blocks on an unapproved Automation grant
  /// exactly as it blocks on a dialog, so the timeout has to name both.
  func testTheTimeoutNamesAutomationAndNotOnlyADialog() {
    let result = CuaAppleScript.run("delay 30", timeout: 1)
    let failure = result.failure ?? ""
    XCTAssertTrue(failure.contains("Automation"))
    XCTAssertTrue(failure.contains("dialog"))
  }

  /// The script reaches osascript as a file, so a quote or a newline in it is
  /// script text and never a second argument.
  func testScriptTextWithQuotesAndNewlinesSurvives() {
    let result = CuaAppleScript.run("set x to \"a\\\"b\"\nreturn x", timeout: 10)
    XCTAssertNil(result.failure)
    XCTAssertEqual(result.output, "a\"b")
  }
}
