import XCTest

@testable import Omi_Computer

final class AppStateListeningTests: XCTestCase {
  override func setUp() {
    super.setUp()
    UserDefaults.standard.removeObject(forKey: .transcriptionPaused)
  }

  override func tearDown() {
    UserDefaults.standard.removeObject(forKey: .transcriptionPaused)
    super.tearDown()
  }

  @MainActor
  func testPauseOverlayPersistsAndReloadsWithoutChangingMode() {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    defer { AssistantSettings.shared.audioRecordingMode = previousMode }
    AssistantSettings.shared.audioRecordingMode = .always
    let appState = AppState()
    XCTAssertFalse(appState.isTranscriptionPaused)
    XCTAssertTrue(appState.isConversationListening)

    appState.toggleConversationListening(source: "ui")

    XCTAssertTrue(appState.isTranscriptionPaused)
    XCTAssertFalse(appState.isConversationListening)
    XCTAssertEqual(appState.audioRecordingMode, .always)
    XCTAssertEqual(UserDefaults.standard.object(forKey: .transcriptionPaused) as? Bool, true)

    let reloadedAppState = AppState()
    XCTAssertTrue(reloadedAppState.isTranscriptionPaused)
    XCTAssertFalse(reloadedAppState.isConversationListening)
    XCTAssertEqual(reloadedAppState.audioRecordingMode, .always)

    reloadedAppState.setConversationListening(true, source: "ui")

    XCTAssertFalse(reloadedAppState.isTranscriptionPaused)
    XCTAssertTrue(reloadedAppState.isConversationListening)
    XCTAssertEqual(reloadedAppState.audioRecordingMode, .always)
    XCTAssertEqual(UserDefaults.standard.object(forKey: .transcriptionPaused) as? Bool, false)
  }

  @MainActor
  func testPauseResumeAcrossEachAudioRecordingModeNeverMutatesModeOrCapture() {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    defer { AssistantSettings.shared.audioRecordingMode = previousMode }
    let frame = Data([1, 2, 3, 4])

    for mode in AssistantSettings.AudioRecordingMode.allCases {
      AssistantSettings.shared.audioRecordingMode = mode
      let appState = AppState()
      appState.isTranscribing = true
      appState.setTranscriptionPaused(false, source: "test")

      XCTAssertEqual(appState.audioRecordingMode, mode)
      XCTAssertTrue(appState.isTranscribing)

      var forwardedFrames: [Data] = []
      appState.forwardConversationAudio(frame) { forwardedFrames.append($0) }
      if mode == .off {
        XCTAssertTrue(
          forwardedFrames.isEmpty,
          "mode Off must not forward transcription audio even when the overlay is live")
        XCTAssertFalse(appState.isConversationListening)
      } else {
        XCTAssertEqual(forwardedFrames, [frame], "\(mode) should forward while the overlay is live")
        XCTAssertTrue(appState.isConversationListening)
      }

      appState.setTranscriptionPaused(true, source: "test")
      forwardedFrames.removeAll()
      appState.forwardConversationAudio(frame) { forwardedFrames.append($0) }

      XCTAssertTrue(forwardedFrames.isEmpty, "\(mode) must gate transcription while paused")
      XCTAssertEqual(appState.audioRecordingMode, mode, "pause must not mutate \(mode)")
      XCTAssertTrue(appState.isTranscribing, "pause must keep capture up in \(mode)")
      XCTAssertFalse(appState.isConversationListening)

      appState.setTranscriptionPaused(false, source: "test")
      forwardedFrames.removeAll()
      appState.forwardConversationAudio(frame) { forwardedFrames.append($0) }

      XCTAssertEqual(appState.audioRecordingMode, mode, "resume must not mutate \(mode)")
      XCTAssertTrue(appState.isTranscribing, "resume must not restart or tear down capture in \(mode)")
      if mode == .off {
        XCTAssertTrue(forwardedFrames.isEmpty)
        XCTAssertFalse(appState.isConversationListening)
      } else {
        XCTAssertEqual(forwardedFrames, [frame], "\(mode) should forward again after resume")
        XCTAssertTrue(appState.isConversationListening)
      }
    }
  }

  @MainActor
  func testListeningStatusStaysActiveWhilePausedSoPauseIsNotOff() {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    defer { AssistantSettings.shared.audioRecordingMode = previousMode }
    AssistantSettings.shared.audioRecordingMode = .always
    let appState = AppState()
    appState.isTranscribing = true
    appState.setTranscriptionPaused(true, source: "test")

    XCTAssertEqual(
      CaptureListeningLogic.listeningStatus(appState: appState), .active,
      "the mode control must stay on while paused — pause is not Off")
    XCTAssertEqual(appState.audioRecordingMode, .always)
  }

  @MainActor
  func testToggleListeningDoesNotWriteAudioRecordingMode() {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    defer { AssistantSettings.shared.audioRecordingMode = previousMode }
    AssistantSettings.shared.audioRecordingMode = .onlyMeetings
    let appState = AppState()
    appState.isTranscribing = true

    appState.toggleConversationListening(source: "hotkey")
    XCTAssertEqual(appState.audioRecordingMode, .onlyMeetings)
    XCTAssertTrue(appState.isTranscriptionPaused)
    XCTAssertTrue(appState.isTranscribing)

    appState.toggleConversationListening(source: "hotkey")
    XCTAssertEqual(appState.audioRecordingMode, .onlyMeetings)
    XCTAssertFalse(appState.isTranscriptionPaused)
    XCTAssertTrue(appState.isTranscribing)
  }

  @MainActor
  func testModeOffPillIsNotPausedAndToggleDoesNotWriteOverlay() {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    defer { AssistantSettings.shared.audioRecordingMode = previousMode }
    AssistantSettings.shared.audioRecordingMode = .off
    let appState = AppState()
    appState.setTranscriptionPaused(false, source: "test")

    let liveOff = CaptureListeningLogic.ConversationListeningPill.state(
      mode: appState.audioRecordingMode,
      isPaused: appState.isTranscriptionPaused
    )
    XCTAssertEqual(liveOff, .off)
    XCTAssertEqual(liveOff.title, "Off")
    XCTAssertNotEqual(liveOff.title, "Paused")
    XCTAssertEqual(
      CaptureListeningLogic.ConversationListeningPill.state(mode: .always, isPaused: true).title,
      "Paused")
    XCTAssertEqual(
      CaptureListeningLogic.ConversationListeningPill.state(mode: .always, isPaused: false).title,
      "Listening")

    let pausedOff = CaptureListeningLogic.ConversationListeningPill.state(mode: .off, isPaused: true)
    XCTAssertEqual(pausedOff, .off)
    XCTAssertEqual(pausedOff.title, "Off")

    appState.toggleConversationListening(source: "ui")
    XCTAssertFalse(appState.isTranscriptionPaused)
    XCTAssertEqual(appState.audioRecordingMode, .off)
    XCTAssertNil(UserDefaults.standard.object(forKey: .transcriptionPaused))
    XCTAssertEqual(
      CaptureListeningLogic.ConversationListeningPill.state(
        mode: appState.audioRecordingMode,
        isPaused: appState.isTranscriptionPaused
      ),
      .off
    )
  }

  @MainActor
  func testPausedListeningDropsAudioFrames() {
    let appState = AppState()
    let frame = Data([1, 2, 3, 4])
    var forwardedFrames: [Data] = []

    appState.setConversationListeningSnapshot(false)
    appState.forwardConversationAudio(frame) { forwardedFrames.append($0) }
    XCTAssertTrue(forwardedFrames.isEmpty)

    appState.setConversationListeningSnapshot(true)
    appState.forwardConversationAudio(frame) { forwardedFrames.append($0) }
    XCTAssertEqual(forwardedFrames, [frame])
  }
}
