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

  /// MIC-02b: too-short PTT / mic-error copy renders in a full-width status
  /// banner under chrome (notch + non-notch), not cramped into the logo lobe.
  func testNotchIslandRendersAndSizesPTTHint() throws {
    let view = try source(relativePath: "Sources/FloatingControlBar/FloatingControlBarView.swift")
    XCTAssertTrue(view.contains("pttStatusBanner"))
    XCTAssertTrue(view.contains("showingPTTStatusBanner"))
    XCTAssertTrue(view.contains("state.isVoiceListening && state.pttHintText.isEmpty"))
    XCTAssertFalse(view.contains("showingNotchPttHint"))
    XCTAssertFalse(view.contains("notchPttHintRow"))
    // Waveform no longer excludes open chat; thinking still does (chat has its own loader).
    XCTAssertFalse(view.contains("!state.isVoiceFollowUp && !state.showingAIConversation"))
    XCTAssertTrue(view.contains("&& !state.showingAIConversation\n            && !state.isVoiceListening"))

    let window = try source(relativePath: "Sources/FloatingControlBar/FloatingControlBarWindow.swift")
    XCTAssertTrue(window.contains("pttHintRowHeight"))
    XCTAssertTrue(window.contains("observePttHint"))
    XCTAssertTrue(window.contains("pttHintSurfaceSize"))
    XCTAssertTrue(window.contains("pttStatusBannerBudget"))
    // Chat-open hints must grow the panel (do not bail out of observePttHint).
    XCTAssertFalse(window.contains("guard !self.state.showingAIConversation else { return }\n                self.resizeAnchored(\n                    to: self.currentSurfaceSizeForCurrentScreen()"))
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
