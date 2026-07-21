import XCTest

@testable import Omi_Computer

#if DEBUG
  // omi-release-compile: this suite drives DEBUG-only test seams (resetForTests); the
  // release-mode notification regression step must compile the bundle without them.

  /// Behavioral coverage for the global-hotkey registration failure boundary.
  ///
  /// `RegisterEventHotKey` (Carbon) cannot be made to return a conflict status in a
  /// hermetic test, so the registration-failure *decision* was extracted into the pure
  /// `GlobalShortcutManager.classifyRegistration` classifier (the controllable seam).
  /// The telemetry contract is then asserted by driving the production
  /// `recordHotkeyRegistrationFailed` wrapper and reading the incident snapshot — the
  /// same hermetic pattern used by `DesktopDiagnosticsManagerTests`.
  final class GlobalShortcutManagerRegistrationTests: XCTestCase {
    override func setUp() {
      super.setUp()
      DesktopDiagnosticsManager.shared.resetForTests()
    }

    override func tearDown() {
      DesktopDiagnosticsManager.shared.resetForTests()
      super.tearDown()
    }

    // MARK: - Registration outcome classifier (pure; no Carbon)

    func testClassifyNoErrWithRefIsRegistered() {
      // The only success path: Carbon reports noErr AND stores a non-nil ref.
      XCTAssertEqual(GlobalShortcutManager.classifyRegistration(noErr, refPresent: true), .registered)
    }

    // MARK: - noErr / nil-ref boundary (the exact regression this suite guards)

    func testClassifyNoErrWithNilRefIsOtherFailure() {
      // Carbon can report noErr without storing an EventHotKeyRef. This is the
      // boundary an independent review flagged: previously classifyRegistration(noErr)
      // returned .registered, so registerHotKey returned .registered and
      // registerAskOmi logged "Registered" for a shortcut that will never fire,
      // even though the else branch had just recorded a registration failure. The
      // prior code treated status==noErr with a nil ref as failure; a registration
      // is successful ONLY when BOTH the status is noErr AND a non-nil ref exists.
      // Driving the pure controllable seam is the prescribed verification — the real
      // Carbon call cannot be made to return noErr with a nil ref hermetically.
      XCTAssertEqual(
        GlobalShortcutManager.classifyRegistration(noErr, refPresent: false), .otherFailure)
    }

    func testClassifyEventHotKeyExistsErrIsConflict() {
      // eventHotKeyExistsErr == -9878 (CarbonEvents.h): another app — or a macOS
      // System Settings > Keyboard > Shortcuts entry, even a disabled one — already
      // owns this (keyCode, modifiers) pair globally. Pure machine axis. The ref is
      // nil on conflict, but the conflict flavor is preserved regardless so the
      // isConflict telemetry discrimination holds.
      XCTAssertEqual(
        GlobalShortcutManager.classifyRegistration(OSStatus(-9878), refPresent: false), .alreadyInUse)
    }

    func testClassifyOtherNonZeroStatusIsOtherFailure() {
      // paramErr (-50) / eventInternalErr (-9870): programmer/runtime errors, not a
      // machine-axis conflict, so they must NOT classify as .alreadyInUse. A nil ref
      // is the norm for these statuses, but the outcome is .otherFailure either way.
      XCTAssertEqual(
        GlobalShortcutManager.classifyRegistration(OSStatus(-50), refPresent: false), .otherFailure)
      XCTAssertEqual(
        GlobalShortcutManager.classifyRegistration(OSStatus(-9870), refPresent: false), .otherFailure)
    }

    // MARK: - Telemetry contract (incident path, NOT recordFallback)

    func testHotKeyConflictRecordsUserVisibleIssueIncident() throws {
      // Cmd+O (keyCode 31) is the default Ask Omi binding; cmdKey == 256 (Carbon Events.h).
      DesktopDiagnosticsManager.shared.recordHotkeyRegistrationFailed(
        osStatus: -9878,
        keycode: 31,
        modifiers: 256,
        isConflict: true)

      let snapshot = try latestSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "user_visible_issue")
      XCTAssertEqual(snapshot["area"] as? String, "startup")
      XCTAssertEqual(snapshot["failure_class"] as? String, "hotkey_conflict")
      XCTAssertEqual(snapshot["phase"] as? String, "startup")
      // osstatus/keycode/modifiers must survive the allowedIncidentExtraKeys filter
      // (a regression here means the incident reaches ops with no Carbon detail).
      XCTAssertEqual(snapshot["osstatus"] as? Int, -9878)
      XCTAssertEqual(snapshot["keycode"] as? Int, 31)
      XCTAssertEqual(snapshot["modifiers"] as? Int, 256)
    }

    func testNonConflictRegistrationFailureClassifiesAsUnknown() throws {
      DesktopDiagnosticsManager.shared.recordHotkeyRegistrationFailed(
        osStatus: -50,
        keycode: 31,
        modifiers: 256,
        isConflict: false)

      let snapshot = try latestSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "user_visible_issue")
      // Non-conflict failures reuse the existing `unknown` label rather than the
      // conflict-specific class, so ops can discriminate the machine-axis cause.
      XCTAssertEqual(snapshot["failure_class"] as? String, "unknown")
      XCTAssertEqual(snapshot["osstatus"] as? Int, -50)
    }

    private func latestSnapshot(
      file: StaticString = #filePath,
      line: UInt = #line
    ) throws -> [String: Any] {
      let url = try XCTUnwrap(
        DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment(),
        file: file,
        line: line)
      defer { try? FileManager.default.removeItem(at: url) }

      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return try XCTUnwrap(snapshots.last, file: file, line: line)
    }
  }
#endif
