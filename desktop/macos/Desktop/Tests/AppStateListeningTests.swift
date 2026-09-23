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

  /// Service-lifecycle contract, not on-device hardware: gated pause keeps mic + BLE
  /// started and the same BLE connection object alive/connected; Off's
  /// `stopAudioCapture` tears capture down. Resume must not restart mic or BLE.
  @MainActor
  func testPausedKeepsMicAndBleCaptureUpUnlikeOff_serviceLifecycleNotHardware() async throws {
    let previousMode = AssistantSettings.shared.audioRecordingMode
    let connection = SessionConnectionDouble(
      device: bluetoothReliabilityTestDevice, sessionGeneration: 1)
    connection.hangAudioStream = true
    defer {
      AssistantSettings.shared.audioRecordingMode = previousMode
      BleAudioService.shared.stopProcessing()
      connection.finishAudioStream()
    }
    AssistantSettings.shared.audioRecordingMode = .always
    let transport = try XCTUnwrap(connection.transport as? ReliabilityTestTransport)
    BleAudioService.shared.stopProcessing()
    try await connection.connect()
    try await transport.connect()
    await BleAudioService.shared.startProcessing(from: connection)

    let appState = AppState()
    let mic = SpyMicCapture()
    appState.audioCaptureService = mic
    appState.audioSource = .bleDevice
    appState.isTranscribing = true
    let bleGeneration = BleAudioService.shared.processingGeneration
    let codec = BleAudioService.shared.currentCodec
    XCTAssertNotNil(codec)
    func assertBleConnectionAliveConnected(file: StaticString = #filePath, line: UInt = #line) async {
      let connectionConnected = await connection.isConnected()
      let transportConnected = await transport.isConnected()
      XCTAssertTrue(
        BleAudioService.shared.processingConnection === connection, file: file, line: line)
      XCTAssertTrue(connectionConnected, file: file, line: line)
      XCTAssertTrue(transportConnected, file: file, line: line)
      XCTAssertEqual(connection.disconnectCallCount, 0, file: file, line: line)
      XCTAssertEqual(transport.disconnectCallCount, 0, file: file, line: line)
    }
    func assertCaptureNotRestarted(file: StaticString = #filePath, line: UInt = #line) {
      XCTAssertEqual(mic.startCount, 0, file: file, line: line)
      XCTAssertEqual(mic.stopCount, 0, file: file, line: line)
      XCTAssertTrue(mic.capturing, file: file, line: line)
      XCTAssertTrue(appState.audioCaptureService === mic, file: file, line: line)
      XCTAssertTrue(appState.isTranscribing, file: file, line: line)
      XCTAssertTrue(BleAudioService.shared.isProcessing, file: file, line: line)
      // An unchanged generation is the load-bearing part: a teardown followed by
      // a fresh startProcessing would bump it, and isProcessing alone cannot see
      // that happen inside the window.
      XCTAssertEqual(
        BleAudioService.shared.processingGeneration, bleGeneration, file: file, line: line)
      XCTAssertEqual(BleAudioService.shared.currentCodec, codec, file: file, line: line)
    }
    await assertBleConnectionAliveConnected()

    appState.toggleConversationListening(source: "ui")

    XCTAssertTrue(appState.isTranscriptionPaused)
    assertCaptureNotRestarted()
    await assertBleConnectionAliveConnected()
    var forwarded: [Data] = []
    appState.forwardConversationAudio(Data([1, 2, 3, 4])) { forwarded.append($0) }
    XCTAssertTrue(forwarded.isEmpty)

    appState.toggleConversationListening(source: "ui")

    XCTAssertFalse(appState.isTranscriptionPaused)
    assertCaptureNotRestarted()
    await assertBleConnectionAliveConnected()
    forwarded.removeAll()
    appState.forwardConversationAudio(Data([1, 2, 3, 4])) { forwarded.append($0) }
    XCTAssertEqual(forwarded, [Data([1, 2, 3, 4])])

    appState.stopAudioCapture()
    XCTAssertFalse(appState.isTranscribing)
    XCTAssertNil(appState.audioCaptureService)
    XCTAssertEqual(mic.stopCount, 1)
    XCTAssertFalse(mic.capturing)
    XCTAssertFalse(BleAudioService.shared.isProcessing)
    XCTAssertNil(BleAudioService.shared.processingConnection)
    XCTAssertNil(BleAudioService.shared.currentCodec)
    XCTAssertEqual(BleAudioService.shared.processingGeneration, bleGeneration)
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

/// Spy for the capture-lifecycle contract. Does not open CoreAudio or a BLE radio.
private final class SpyMicCapture: AudioCaptureService, @unchecked Sendable {
  private(set) var startCount = 0
  private(set) var stopCount = 0
  override var capturing: Bool { stopCount == 0 }
  override func startCapture(
    onAudioChunk: @escaping AudioChunkHandler, onAudioLevel: AudioLevelHandler? = nil
  ) async throws {
    startCount += 1
  }
  override func stopCapture() { stopCount += 1 }
}
