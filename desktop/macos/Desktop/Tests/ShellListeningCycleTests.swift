import XCTest

@testable import Omi_Computer

/// The listening control is a **three-mode cycle**, and these are the tests of the rule it broke.
///
/// `AudioRecordingMode` has had three cases for a while, but the control only ever reached two of
/// them: it flipped between `.off` and `.onlyMeetings`, so `.always` was unreachable from the top
/// bar and from Home. Turning the microphone "on" therefore always armed the meetings gate — which
/// holds the microphone shut until a call is detected — and there was no way to ask for continuous
/// capture from either shell.
///
/// The cycle and the mode naming are pure functions, so every assertion here runs the production
/// decision rather than scraping a view's source for a string.
@MainActor
final class ShellListeningCycleTests: XCTestCase {

  // MARK: The cycle

  /// The regression test. Three steps from `.off` must visit `.always` and `.onlyMeetings` and
  /// land back on `.off`; the shipped two-state flip produces `off → onlyMeetings → off` and fails
  /// at the first step.
  func testTheCycleVisitsAllThreeModesAndReturns() {
    let first = CaptureListeningLogic.nextAudioRecordingMode(after: .off)
    let second = CaptureListeningLogic.nextAudioRecordingMode(after: first)
    let third = CaptureListeningLogic.nextAudioRecordingMode(after: second)

    XCTAssertEqual(
      [first, second, third], [.always, .onlyMeetings, .off],
      """
      the listening cycle ran off → \(first) → \(second) → \(third). It has to offer all three \
      modes: the reported bug is that "always on" was unreachable because the control only ever \
      flipped between off and only-meetings.
      """)
  }

  /// Stated on its own because it is the exact user-visible symptom: the first click from off must
  /// start recording, not arm a gate that keeps the microphone shut.
  func testTurningItOnFromOffSelectsAlwaysRatherThanOnlyMeetings() {
    XCTAssertEqual(
      CaptureListeningLogic.nextAudioRecordingMode(after: .off), .always,
      "turning the microphone on must start recording, not silently arm a gate that keeps it shut")
  }

  /// Every mode must reach every other mode by clicking. A cycle with a mode that cannot be left,
  /// or one that is never visited, is the same defect in a different position.
  func testEveryModeIsReachableFromEveryOtherMode() {
    for start in AssistantSettings.AudioRecordingMode.allCases {
      var seen: [AssistantSettings.AudioRecordingMode] = []
      var mode = start
      for _ in 0..<3 {
        mode = CaptureListeningLogic.nextAudioRecordingMode(after: mode)
        seen.append(mode)
      }
      XCTAssertEqual(
        Set(seen).count, AssistantSettings.AudioRecordingMode.allCases.count,
        "from \(start) three clicks reached \(seen) — a click must never leave a mode unreachable")
      XCTAssertEqual(mode, start, "from \(start) three clicks landed on \(mode) rather than home")
    }
  }

  /// The cycle must cover whatever `AudioRecordingMode` actually has. If a fourth mode is added,
  /// this fails rather than letting it silently become unreachable the way `.always` was.
  func testTheCycleCoversEveryDeclaredMode() {
    var seen: Set<AssistantSettings.AudioRecordingMode> = [.off]
    var mode = AssistantSettings.AudioRecordingMode.off
    for _ in 0..<AssistantSettings.AudioRecordingMode.allCases.count {
      mode = CaptureListeningLogic.nextAudioRecordingMode(after: mode)
      seen.insert(mode)
    }
    XCTAssertEqual(
      seen, Set(AssistantSettings.AudioRecordingMode.allCases),
      """
      the cycle visits \(seen.count) of \(AssistantSettings.AudioRecordingMode.allCases.count) \
      declared modes. A mode the control cannot select is a mode the user does not have.
      """)
  }

  // MARK: Reading the mode back off the default

  func testAnUnknownPersistedModeFallsBackToTheGatedMode() {
    XCTAssertEqual(
      CaptureListeningLogic.audioRecordingMode(raw: "nonsense"), .onlyMeetings,
      "an unreadable persisted mode must fall back to the gated mode, never to continuous capture")
  }

  func testEachDeclaredModeSurvivesARoundTripThroughItsRawValue() {
    for mode in AssistantSettings.AudioRecordingMode.allCases {
      XCTAssertEqual(
        CaptureListeningLogic.audioRecordingMode(raw: mode.rawValue), mode,
        "\(mode) did not survive a round trip through the persisted default")
    }
  }

  // MARK: The mark

  /// Only Meetings is the mode whose behaviour the glyph cannot state — the control is switched on
  /// while the microphone is held shut — so it is the one mode that carries a mark. The others must
  /// not, or the mark stops meaning anything.
  func testOnlyMeetingsCarriesTheModeBadgeAndNothingElseDoes() {
    XCTAssertEqual(
      ShellStatusGlyph.modeBadge(for: .onlyMeetings), ShellStatusGlyph.meetingsOnly,
      "Only Meetings must be distinguishable from Always On at a glance")
    XCTAssertNil(
      ShellStatusGlyph.modeBadge(for: .always),
      "Always On must not wear the meetings mark — the two modes would be indistinguishable")
    XCTAssertNil(ShellStatusGlyph.modeBadge(for: .off), "the off mode is said by the slash")
  }

  /// The mark rides in the corner; the silhouette underneath stays the one `mic` the cluster's
  /// header pins. `ShellStatusIconLegibilityTests` measures that in pixels — this is the
  /// type-level half: adding a mode must never add a listening glyph.
  func testTheModeBadgeIsNeverTheListeningGlyphItself() {
    XCTAssertNotEqual(
      ShellStatusGlyph.modeBadge(for: .onlyMeetings), ShellStatusGlyph.listening,
      """
      the meetings mark replaced the listening glyph instead of riding on top of it — that is the \
      `waveform`/`mic` silhouette swap the cluster's header rejects, returning as a mode badge.
      """)
    XCTAssertEqual(
      ShellStatusGlyph.listening, "mic",
      "the listening control has exactly one silhouette, in every state and every mode")
  }

  // MARK: The promise the tooltip makes

  /// A wordless control's tooltip is the only place a click's outcome is written down, so it has to
  /// name where the click actually goes. "Click to stop" was true of a two-state switch and is a
  /// false promise from Always On, where a click selects Only Meetings and stops nothing.
  func testTheTooltipNamesTheModeAClickMovesTo() {
    func tooltip(from mode: AssistantSettings.AudioRecordingMode, state: HomeStatusState) -> String {
      ShellStatusTooltip.audio(
        state: state,
        mode: CaptureListeningLogic.audioRecordingModeTitle(mode),
        next: CaptureListeningLogic.audioRecordingModeTitle(
          CaptureListeningLogic.nextAudioRecordingMode(after: mode)))
    }

    let fromAlways = tooltip(from: .always, state: .active)
    XCTAssertTrue(
      fromAlways.contains("Only Meetings"),
      """
      the tooltip while always-on reads "\(fromAlways)" — a click there selects Only Meetings, and \
      a tooltip that says anything else promises something the click does not do.
      """)

    let fromMeetings = tooltip(from: .onlyMeetings, state: .active)
    XCTAssertTrue(
      fromMeetings.contains("Off"),
      "the tooltip in Only Meetings reads \"\(fromMeetings)\" — a click there switches it off")

    let fromOff = tooltip(from: .off, state: .inactive)
    XCTAssertTrue(
      fromOff.contains("Always On"),
      "the tooltip while off reads \"\(fromOff)\" — a click there starts continuous recording")
  }

  /// Each mode has to be nameable in the sentence, and no two may share a name.
  func testTheThreeModesHaveThreeDistinctNames() {
    let titles = AssistantSettings.AudioRecordingMode.allCases.map {
      CaptureListeningLogic.audioRecordingModeTitle($0)
    }
    XCTAssertEqual(Set(titles).count, titles.count, "modes must not share a name: \(titles)")
    XCTAssertFalse(titles.contains { $0.isEmpty }, "every mode has to be nameable in the tooltip")
  }

  /// Without the microphone grant the first click opens the permission prompt and the mode does
  /// not advance, so the tooltip must not name a mode that click will not reach.
  func testTheTooltipDoesNotPromiseAModeAClickCannotReachWithoutPermission() {
    let denied = ShellStatusTooltip.audio(
      state: .inactive, mode: "Off", next: "Always On", hasMicrophonePermission: false)
    XCTAssertFalse(
      denied.contains("Always On"),
      "the tooltip reads \"\(denied)\" while the microphone grant is missing — that click opens "
        + "the permission prompt and leaves the mode where it was, so naming the next mode is a "
        + "promise the click cannot keep.")
    XCTAssertTrue(
      denied.localizedCaseInsensitiveContains("microphone"),
      "it has to say what is actually missing: \(denied)")

    let granted = ShellStatusTooltip.audio(
      state: .inactive, mode: "Off", next: "Always On", hasMicrophonePermission: true)
    XCTAssertTrue(
      granted.contains("Always On"),
      "with permission granted the click really does select the next mode: \(granted)")
  }

  /// Only Meetings must not keep a microphone open while it cannot yet prove a call is running.
  /// Selecting it from a live Always session builds a fresh detector, so the first reconcile pass
  /// sees `meetingStateReady == false` — the moment this guards.
  func testOnlyMeetingsPausesCaptureUntilTheMeetingGateHasAnswered() {
    XCTAssertTrue(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .onlyMeetings, meetingStateReady: false),
      "switching to Only Meetings before the detector has reported left capture running. "
        + "\"Not known yet\" has to mean \"not in a call\" for a gate the user selected in order "
        + "to close the microphone.")
    XCTAssertFalse(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .onlyMeetings, meetingStateReady: true),
      "once the detector has reported, the normal gating decides")
    XCTAssertFalse(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .always, meetingStateReady: false),
      "Always On is not gated on meetings and must not be paused by an unready detector")
    XCTAssertFalse(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .off, meetingStateReady: false),
      "Off is stopped by the session teardown, not by this pause")
  }

  /// The hint exists because Only Meetings is the one mode whose behaviour is invisible: the
  /// control reads as on while nothing is being recorded. If it stops saying so, it is decoration.
  func testTheMeetingsHintExplainsThatTheMicrophoneStaysClosed() {
    let hint = ShellStatusIcons.meetingsHint
    XCTAssertTrue(
      hint.localizedCaseInsensitiveContains("until"),
      """
      the Only Meetings hint reads "\(hint)" and no longer says the microphone waits for something. \
      That wait is the whole of what distinguishes this mode from Always On.
      """)
    XCTAssertTrue(
      hint.localizedCaseInsensitiveContains("call")
        || hint.localizedCaseInsensitiveContains("meeting"),
      "the hint has to name what the microphone is waiting for: \(hint)")
  }
}
