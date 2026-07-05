import XCTest

@testable import Omi_Computer

/// Guards the fix for the too-short PTT tap (BL-031 / MIC-02): a press+release
/// faster than capture spins up produces a turn with no usable audio. `finalize()`
/// discards such turns in each mode's silence gate (hub / omni / batch). All gates
/// now route a *too-short* turn (below `minTurnAudioSeconds`) to
/// `finishTooShortPTTTurnWithHint(reason:)`, which shows "Hold longer to record" via
/// the bar's `pttHintText` and resets after ~2s; longer-but-quiet turns keep the
/// quiet reset.
///
/// The hint renders through a dedicated `FloatingControlBarState.pttHintText` bound
/// in `FloatingControlBarView` — the legacy `voiceTranscript` field is write-only and
/// displayed by no view. `PushToTalkManager` is a `@MainActor` singleton not
/// constructible in a unit test, so these are source-scrape assertions (the same
/// pattern as `PushToTalkStateMachineTests`). User-visible behavior is verified at
/// runtime on a named bundle in the default (hub) config — see
/// `.omi-hardening/slices/003-ptt-empty-batch/`.
final class PTTAudioCaptureRaceTests: XCTestCase {
  func testAllModeGatesRouteTooShortTurnsToHint() throws {
    let source = try managerSource()

    // hub, omni/batch, and the empty-buffer backstop all route to the hint.
    let hintCalls = source.components(separatedBy: "finishTooShortPTTTurnWithHint(reason:").count - 1
    XCTAssertGreaterThanOrEqual(hintCalls, 3)
    // Only when the turn was too short — reusing the existing threshold.
    XCTAssertTrue(source.contains("if totalSec < Self.minTurnAudioSeconds {"))
    XCTAssertTrue(source.contains("reason: \"hub"))
  }

  func testHintUsesPTTHintTextAndKeepsBarVoiceSized() throws {
    let source = try managerSource()

    XCTAssertTrue(source.contains("private func finishTooShortPTTTurnWithHint(reason: String)"))
    XCTAssertTrue(source.contains("barState?.pttHintText = \"Hold longer to record\""))
    // updateBarState keeps the bar in voice-UI (sized) while the hint is up.
    XCTAssertTrue(source.contains("|| !barState.pttHintText.isEmpty"))
    // The hint is cleared on reset.
    XCTAssertTrue(source.contains("barState?.pttHintText = \"\""))
  }

  /// Review fixes for the hint path (cubic P1/P2): the omni/batch discard path
  /// leaves the manager in `.finalizing`, so the hint must reset `state` to idle
  /// (or a new press inside the 2s window is dropped — `handleShortcutDown` ignores
  /// `.finalizing`), and the reset timer must be tagged so a rapid follow-up tap's
  /// hint isn't cleared early.
  func testHintPathResetsStateAndTagsHint() throws {
    let source = try managerSource()
    guard let start = source.range(of: "func finishTooShortPTTTurnWithHint(reason: String)") else {
      return XCTFail("finishTooShortPTTTurnWithHint not found")
    }
    let body = String(source[start.lowerBound...].prefix(900))
    XCTAssertTrue(body.contains("state = .idle"), "hint path must return the manager to .idle")
    XCTAssertTrue(body.contains("pttHintGeneration"), "hint reset must be guarded by a per-hint token")
  }

  func testFloatingBarRendersPTTHintText() throws {
    let view = try source(relativePath: "Sources/FloatingControlBar/FloatingControlBarView.swift")
    XCTAssertTrue(view.contains("state.pttHintText"))
    XCTAssertTrue(view.contains("Text(state.pttHintText)"))
    let state = try source(relativePath: "Sources/FloatingControlBar/FloatingControlBarState.swift")
    XCTAssertTrue(state.contains("var pttHintText: String"))
  }

  /// MIC-02b: the notch-island layout bypasses the pill's `voiceListeningView`, so the
  /// hint must render as its own row below the notch chrome (`notchPttHintRow`), the
  /// surface must count as expanded so it draws, and the window must grow to fit it —
  /// otherwise the hint is clipped to zero height and never seen on a notched Mac.
  func testNotchIslandRendersAndSizesPTTHint() throws {
    let view = try source(relativePath: "Sources/FloatingControlBar/FloatingControlBarView.swift")
    // Dedicated notch hint row, gated on the notch layout + a non-empty hint.
    XCTAssertTrue(view.contains("notchPttHintRow"))
    XCTAssertTrue(view.contains("state.usesNotchIsland && !state.pttHintText.isEmpty"))
    // The hint keeps the unified surface in its expanded (drawn) state.
    XCTAssertTrue(view.contains("|| !state.pttHintText.isEmpty"))

    let window = try source(relativePath: "Sources/FloatingControlBar/FloatingControlBarWindow.swift")
    // All three sizing paths grow for the hint...
    let sizedBranches = window.components(separatedBy: "!state.pttHintText.isEmpty").count - 1
    XCTAssertGreaterThanOrEqual(sizedBranches, 3)
    // ...using a dedicated hint-row height...
    XCTAssertTrue(window.contains("pttHintRowHeight"))
    // ...and a dedicated observer resizes when the hint appears/clears (no
    // isVoiceListening transition fires on its own to trigger a resize).
    XCTAssertTrue(window.contains("state.$pttHintText"))
  }

  private func managerSource() throws -> String {
    try source(relativePath: "Sources/FloatingControlBar/PushToTalkManager.swift")
  }

  private func source(relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }
}
