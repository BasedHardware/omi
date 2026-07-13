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
  func testDeferredCoreAudioReconfigurationCannotRestartAfterOwnerTeardown() {
    XCTAssertTrue(
      AudioCaptureService.shouldRunDeferredReconfiguration(
        isCapturing: true,
        isReconfiguring: true))
    XCTAssertFalse(
      AudioCaptureService.shouldRunDeferredReconfiguration(
        isCapturing: false,
        isReconfiguring: true))
    XCTAssertFalse(
      AudioCaptureService.shouldRunDeferredReconfiguration(
        isCapturing: true,
        isReconfiguring: false))
  }

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
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    let started = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model

    let finished = reducer.reduce(started, .finish(turnID: turnID, reason: .tooShort))

    XCTAssertEqual(finished.model.turn?.phase, .terminal(.tooShort))
    XCTAssertEqual(finished.model.turn?.projection.hint, "Hold longer to record")
    XCTAssertTrue(finished.model.turn?.deadlines.contains(.hintVisibility) == true)
  }

  /// Review fixes for the hint path (cubic P1/P2): the omni/batch discard path
  /// leaves the manager in `.finalizing`, so the hint must reset `state` to idle
  /// (or a new press inside the 2s window is dropped — `handleShortcutDown` ignores
  /// `.finalizing`), and the reset timer must be tagged so a rapid follow-up tap's
  /// hint isn't cleared early.
  func testHintPathResetsStateAndTagsHint() throws {
    let reducer = VoiceTurnReducer()
    let turnID = VoiceTurnID()
    var model = reducer.reduce(.idle, .start(turnID: turnID, ownerID: nil, intent: .hold)).model
    model = reducer.reduce(model, .finish(turnID: turnID, reason: .tooShort)).model

    XCTAssertTrue(model.turn?.phase.isTerminal == true)

    let cleared = reducer.reduce(
      model,
      .deadlineFired(turnID: turnID, deadline: .hintVisibility))
    XCTAssertEqual(cleared.model.turn?.projection.hint, "")
    XCTAssertEqual(cleared.model.turn?.phase, .terminal(.tooShort))
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
    XCTAssertTrue(window.contains("state.$voiceProjection"))
    XCTAssertTrue(window.contains("$0.hint.isEmpty"))
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
