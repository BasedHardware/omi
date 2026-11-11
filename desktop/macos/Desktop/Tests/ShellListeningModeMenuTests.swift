import AppKit
import SwiftUI
import XCTest

@testable import Omi_Computer

/// The top bar's microphone opens a menu naming the three recording modes; it never cycles.
///
/// It used to advance Off → Always On → Only Meetings on each click, with no menu and no
/// confirmation, so one stray click could turn on always-on room recording. These tests run the
/// production selection path (`CaptureListeningLogic.selectListeningMode`) with its side effects
/// recorded instead of performed, the menu's own row and keyboard model, and the tooltip wording.
@MainActor
final class ShellListeningModeMenuTests: XCTestCase {

  private typealias Mode = AssistantSettings.AudioRecordingMode

  /// Everything a selection would do to the world, captured instead of done: no TCC prompt, no
  /// write to the user's real recording mode, no analytics event.
  @MainActor
  private final class Recorder {
    var raw: String
    var isToggling = false
    var permissionRequests = 0
    var persisted: [Mode] = []
    var tracked: [Mode] = []

    init(mode: Mode) { raw = mode.rawValue }

    var effects: CaptureListeningLogic.ListeningModeEffects {
      CaptureListeningLogic.ListeningModeEffects(
        requestMicrophonePermission: { _ in self.permissionRequests += 1 },
        persist: { self.persisted.append($0) },
        track: { self.tracked.append($0) })
    }

    var rawBinding: Binding<String> {
      Binding(get: { self.raw }, set: { self.raw = $0 })
    }

    var togglingBinding: Binding<Bool> {
      Binding(get: { self.isToggling }, set: { self.isToggling = $0 })
    }
  }

  private func select(
    _ mode: Mode, from start: Mode, hasMicrophonePermission: Bool
  ) -> (CaptureListeningLogic.ListeningModeSelection, Recorder) {
    let appState = AppState()
    appState.hasMicrophonePermission = hasMicrophonePermission
    let recorder = Recorder(mode: start)
    let outcome = CaptureListeningLogic.selectListeningMode(
      mode, appState: appState, audioRecordingModeRaw: recorder.rawBinding,
      isTogglingListening: recorder.togglingBinding, effects: recorder.effects)
    return (outcome, recorder)
  }

  // MARK: Selecting a mode

  /// Every mode is reachable in one choice from every other mode, and the choice lands on exactly
  /// the mode chosen: the stored default, the shared setting and the analytics event all agree.
  func testSelectingEachModeAppliesIt() {
    for start in Mode.allCases {
      for target in Mode.allCases where target != start {
        let (outcome, recorder) = select(target, from: start, hasMicrophonePermission: true)
        let context = "choosing \(target) from \(start)"
        XCTAssertEqual(outcome, .apply(target), context)
        XCTAssertEqual(recorder.raw, target.rawValue, "\(context) did not update the stored mode")
        XCTAssertEqual(recorder.persisted, [target], "\(context) did not reach AssistantSettings")
        XCTAssertEqual(recorder.tracked, [target], "\(context) was not reported to analytics")
        XCTAssertEqual(recorder.permissionRequests, 0, "\(context) prompted with the grant in hand")
        XCTAssertTrue(recorder.isToggling, "\(context) should show the control busy while it applies")
      }
    }
  }

  /// Without the microphone grant, choosing a recording mode is spent on the permission request,
  /// and the mode stays where it was: a mode that cannot record must not look selected.
  func testSelectingAModeThatNeedsTheMicWithoutPermissionRequestsItAndDoesNotMove() {
    for target in [Mode.always, .onlyMeetings] {
      let (outcome, recorder) = select(target, from: .off, hasMicrophonePermission: false)
      XCTAssertEqual(outcome, .needsMicrophonePermission, "choosing \(target) without the grant")
      XCTAssertEqual(recorder.permissionRequests, 1, "choosing \(target) must ask for the microphone")
      XCTAssertEqual(recorder.raw, Mode.off.rawValue, "choosing \(target) moved the mode anyway")
      XCTAssertTrue(recorder.persisted.isEmpty, "choosing \(target) wrote \(recorder.persisted)")
      XCTAssertTrue(recorder.tracked.isEmpty, "choosing \(target) reported a change that did not happen")
    }
  }

  /// Turning recording off needs no grant, so it is never blocked by a missing one.
  func testSelectingOffNeverWaitsForThePermission() {
    let (outcome, recorder) = select(.off, from: .always, hasMicrophonePermission: false)
    XCTAssertEqual(outcome, .apply(.off))
    XCTAssertEqual(recorder.raw, Mode.off.rawValue)
    XCTAssertEqual(recorder.permissionRequests, 0)
  }

  /// Choosing the mode that is already selected changes nothing and reports nothing.
  func testReselectingTheCurrentModeIsANoOp() {
    for mode in Mode.allCases {
      let (outcome, recorder) = select(mode, from: mode, hasMicrophonePermission: true)
      XCTAssertEqual(outcome, .unchanged, "re-choosing \(mode)")
      XCTAssertTrue(recorder.persisted.isEmpty)
      XCTAssertTrue(recorder.tracked.isEmpty)
      XCTAssertFalse(recorder.isToggling)
    }
  }

  /// Re-choosing a recording mode whose grant was revoked is a request to make it work, so it asks.
  func testReselectingARecordingModeWithoutTheGrantAsksForIt() {
    let (outcome, recorder) = select(.always, from: .always, hasMicrophonePermission: false)
    XCTAssertEqual(outcome, .needsMicrophonePermission)
    XCTAssertEqual(recorder.permissionRequests, 1)
  }

  // MARK: The menu's rows

  /// The menu lists every declared mode, in order, then the settings link last. A mode the menu does
  /// not list is a mode the user does not have.
  func testTheMenuListsEveryModeThenAudioSettings() {
    XCTAssertEqual(
      ShellListeningMenuItem.all,
      Mode.allCases.map(ShellListeningMenuItem.mode) + [.audioSettings])
    XCTAssertEqual(ShellListeningMenuItem.audioSettings.title, "Audio Settings…")
  }

  /// Each row names its mode with the same title Settings uses, and says what it records.
  func testEveryModeRowIsNamedAndSaysWhatItRecords() {
    var details: Set<String> = []
    for mode in Mode.allCases {
      let item = ShellListeningMenuItem.mode(mode)
      XCTAssertEqual(item.title, CaptureListeningLogic.audioRecordingModeTitle(mode))
      guard let detail = item.detail else {
        XCTFail("\(mode) has no line saying what it records")
        continue
      }
      XCTAssertFalse(detail.hasSuffix("."), "descriptions carry no trailing period: \(detail)")
      details.insert(detail)
    }
    XCTAssertEqual(details.count, Mode.allCases.count, "two modes describe themselves the same way")
    XCTAssertEqual(
      Set(Mode.allCases.map(CaptureListeningLogic.audioRecordingModeTitle)).count,
      Mode.allCases.count, "modes must not share a name")
  }

  /// The highlight opens on the current mode, so Return on open changes nothing.
  func testTheHighlightOpensOnTheCurrentMode() {
    for mode in Mode.allCases {
      let index = ShellListeningMenuItem.initialHighlight(current: mode)
      XCTAssertEqual(ShellListeningMenuItem.all[index], .mode(mode))
    }
  }

  /// Arrow keys walk every row and wrap at both ends.
  func testArrowKeysWalkEveryRowAndWrap() {
    let count = ShellListeningMenuItem.all.count
    var index = 0
    var visited: [Int] = []
    for _ in 0..<count {
      index = ShellListeningMenuItem.highlight(movingFrom: index, by: 1)
      visited.append(index)
    }
    XCTAssertEqual(Set(visited).count, count, "↓ did not reach every row: \(visited)")
    XCTAssertEqual(index, 0, "↓ from the last row must wrap to the first")
    XCTAssertEqual(ShellListeningMenuItem.highlight(movingFrom: 0, by: -1), count - 1)
  }

  // MARK: The glyph

  /// The mic is the control's name in every mode. Only Meetings used to swap it for
  /// `person.2.fill`, which read like a People button; it now wears a badge on the mic instead.
  func testTheGlyphIsTheMicInEveryModeAndOnlyMeetingsWearsABadge() {
    XCTAssertEqual(ShellStatusGlyph.listening, "mic")
    XCTAssertNil(ShellStatusGlyph.listeningBadge(for: .off), "off is said by the slash")
    XCTAssertNil(ShellStatusGlyph.listeningBadge(for: .always), "Always On is the plain mic")
    guard let badge = ShellStatusGlyph.listeningBadge(for: .onlyMeetings) else {
      return XCTFail("Only Meetings must be distinguishable from Always On")
    }
    XCTAssertFalse(badge.hasPrefix("person"), "a people mark reads as a People button")
    XCTAssertNotNil(NSImage(systemSymbolName: badge, accessibilityDescription: nil), "\(badge) is not a symbol")
  }

  // MARK: The sentence

  /// The tooltip promises the menu, never a particular next mode.
  func testTheAudioTooltipPromisesTheMenuInEveryClickableState() {
    for state in [HomeStatusState.active, .armed, .inactive] {
      for permission in [true, false] {
        let tooltip = ShellStatusTooltip.audio(
          state: state, mode: "Only Meetings", hasMicrophonePermission: permission)
        XCTAssertTrue(tooltip.hasPrefix("Audio"), tooltip)
        XCTAssertTrue(tooltip.hasSuffix(ShellStatusTooltip.audioOpensMenu), tooltip)
        XCTAssertFalse(tooltip.contains("Click for"), "the click opens a menu: \(tooltip)")
      }
    }
    let blocked = ShellStatusTooltip.audio(state: .blocked, mode: "Always On")
    XCTAssertTrue(blocked.contains("Settings"), "a blocked click opens Settings: \(blocked)")
  }

  /// Armed is on but not recording, so it says it is waiting for a call, and without the grant
  /// it names what is missing rather than promising a recording.
  func testTheArmedTooltipSaysItIsWaitingForACall() {
    let armed = ShellStatusTooltip.audio(state: .armed, mode: "Only Meetings")
    XCTAssertTrue(armed.contains("waiting for a call"), armed)
    XCTAssertFalse(armed.contains("recording ("), "nothing is recorded yet: \(armed)")

    let ungranted = ShellStatusTooltip.audio(
      state: .armed, mode: "Only Meetings", hasMicrophonePermission: false)
    XCTAssertTrue(ungranted.localizedCaseInsensitiveContains("microphone"), ungranted)
    XCTAssertFalse(ungranted.contains("Recording starts"), ungranted)
  }

  func testTheRecordingTooltipCarriesItsMode() {
    let tooltip = ShellStatusTooltip.audio(state: .active, mode: "Always On")
    XCTAssertTrue(tooltip.contains("recording (Always On)"), tooltip)
  }

  // MARK: Reading the mode back off the default

  func testAnUnknownPersistedModeFallsBackToTheGatedMode() {
    XCTAssertEqual(
      CaptureListeningLogic.audioRecordingMode(raw: "nonsense"), .onlyMeetings,
      "an unreadable persisted mode must fall back to the gated mode, never to continuous capture")
  }

  func testEachDeclaredModeSurvivesARoundTripThroughItsRawValue() {
    for mode in Mode.allCases {
      XCTAssertEqual(CaptureListeningLogic.audioRecordingMode(raw: mode.rawValue), mode)
    }
  }

  /// Only Meetings must not keep a microphone open while it cannot yet prove a call is running.
  /// Selecting it from a live Always session builds a fresh detector, so the first reconcile pass
  /// sees `meetingStateReady == false`, the moment this guards.
  func testOnlyMeetingsPausesCaptureUntilTheMeetingGateHasAnswered() {
    XCTAssertTrue(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .onlyMeetings, meetingStateReady: false))
    XCTAssertFalse(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .onlyMeetings, meetingStateReady: true))
    XCTAssertFalse(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .always, meetingStateReady: false))
    XCTAssertFalse(
      MeetingGateReadinessPolicy.shouldPauseCapture(mode: .off, meetingStateReady: false))
  }
}
