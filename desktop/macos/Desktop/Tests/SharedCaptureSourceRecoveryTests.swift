import CoreAudio
import XCTest

@testable import Omi_Computer

private actor CaptureStopGate {
  private var release: CheckedContinuation<Void, Never>?
  private var observer: CheckedContinuation<Void, Never>?

  func block() async {
    await withCheckedContinuation { continuation in
      release = continuation
      observer?.resume()
      observer = nil
    }
  }

  func waitUntilBlocked() async {
    if release != nil { return }
    await withCheckedContinuation { observer = $0 }
  }

  func unblock() {
    release?.resume()
    release = nil
  }
}

private final class RecoveryMicrophone: AudioCaptureService, @unchecked Sendable {
  private let lock = NSLock()
  private var stopped = false
  let gate: CaptureStopGate?

  init(gate: CaptureStopGate? = nil) {
    self.gate = gate
    super.init()
  }

  override var capturing: Bool { !lock.withLock { stopped } }
  override var activeDeviceID: AudioDeviceID { 7 }
  override func stopCapture() { lock.withLock { stopped = true } }
  override func waitForPhysicalStop() async { await gate?.block() }
}

@available(macOS 14.4, *)
private final class RecoverySystemAudio: SystemAudioCaptureService, @unchecked Sendable {
  private let lock = NSLock()
  private var stopped = false
  let live: Bool
  init(live: Bool = true) { self.live = live }
  override var capturing: Bool { !lock.withLock { stopped } }
  override var hasRecentAudioFrames: Bool { capturing && live }
  override func stopCapture() { lock.withLock { stopped = true } }
}

@MainActor
final class SharedCaptureSourceRecoveryTests: XCTestCase {
  private func effects(replacement: AudioCaptureService) -> CoreAudioCaptureRecoveryEffects {
    CoreAudioCaptureRecoveryEffects(makeMicrophone: { _ in replacement }, armCapture: { _ in })
  }

  func testMicrophoneRecoveryPreservesTapMixerAndRecordingIdentity() async throws {
    guard #available(macOS 14.4, *) else { throw XCTSkip("Core Audio taps require macOS 14.4") }
    let state = AppState()
    let oldMic = RecoveryMicrophone()
    let newMic = RecoveryMicrophone()
    let tap = RecoverySystemAudio()
    let mixer = AudioMixer(clock: { 10 })
    var emitted: [Data] = []
    mixer.start { emitted.append($0) }
    // Less than one output chunk. A full rebuild would flush these buffers.
    mixer.setSystemAudio(Data(repeating: 1, count: 1600))
    mixer.setMicAudio(Data(repeating: 0, count: 1600))
    state.isTranscribing = true
    state.currentSessionId = 42
    state.recordingGeneration = 19
    state.audioCaptureService = oldMic
    state.systemAudioCaptureService = tap
    state.audioMixer = mixer
    let attempt = CaptureAttemptOutcomeState(mode: "always", intent: .userStart)
    state.captureAttempt = attempt

    let restarted = await state.rebuildCoreAudioCaptureStack(
      reason: "silent input", scope: .microphone, effects: effects(replacement: newMic))

    XCTAssertTrue(restarted)
    XCTAssertFalse(oldMic.capturing)
    XCTAssertTrue(state.audioCaptureService === newMic)
    XCTAssertTrue((state.systemAudioCaptureService as? RecoverySystemAudio) === tap)
    XCTAssertTrue(tap.capturing)
    XCTAssertTrue(state.audioMixer === mixer)
    XCTAssertTrue(emitted.isEmpty, "mic recovery must not flush or reset the system stream's clock")
    mixer.setSystemAudio(Data(repeating: 1, count: 1600))
    mixer.setMicAudio(Data(repeating: 0, count: 1600))
    XCTAssertEqual(emitted, [Data(repeating: 1, count: 3200)], "pending system PCM must survive recovery")
    XCTAssertTrue(state.isTranscribing)
    XCTAssertEqual(state.currentSessionId, 42)
    XCTAssertEqual(state.recordingGeneration, 19)
    XCTAssertEqual(state.captureAttempt?.attemptId, attempt.attemptId)
    mixer.stop()
  }

  func testFullRecoveryStillRebindsAllSourcesForConversationRotation() async throws {
    guard #available(macOS 14.4, *) else { throw XCTSkip("Core Audio taps require macOS 14.4") }
    let state = AppState()
    let oldMic = RecoveryMicrophone()
    let tap = RecoverySystemAudio()
    let mixer = AudioMixer()
    state.isTranscribing = true
    state.audioCaptureService = oldMic
    state.systemAudioCaptureService = tap
    state.audioMixer = mixer

    await state.rebuildCoreAudioCaptureStack(
      reason: "local_conversation_rotation", effects: effects(replacement: RecoveryMicrophone()))

    XCTAssertFalse(tap.capturing)
    XCTAssertNil(state.systemAudioCaptureService)
    XCTAssertTrue(state.audioMixer !== mixer)
    XCTAssertTrue(state.isTranscribing)
  }

  func testLocalMicrophoneRecoveryPreservesBothTranscriptionSinks() async throws {
    guard #available(macOS 14.4, *) else { throw XCTSkip("Core Audio taps require macOS 14.4") }
    let state = AppState()
    let micSTT = LocalTranscriptionService(language: .english, isUser: true)
    let systemSTT = LocalTranscriptionService(language: .english, isUser: false)
    let tap = RecoverySystemAudio()
    state.isTranscribing = true
    state.sttSession.activeMode = .local
    state.audioCaptureService = RecoveryMicrophone()
    state.localMicService = micSTT
    state.localSystemService = systemSTT
    state.systemAudioCaptureService = tap

    await state.rebuildCoreAudioCaptureStack(
      reason: "silent", scope: .microphone, effects: effects(replacement: RecoveryMicrophone()))

    XCTAssertTrue(state.sttSession.useLocalSTT)
    XCTAssertTrue(state.localMicService === micSTT)
    XCTAssertTrue(state.localSystemService === systemSTT)
    XCTAssertTrue(tap.capturing)
    XCTAssertNil(state.audioMixer, "local recovery cannot introduce a cloud mixer")
  }

  func testTeardownCompletionCannotResurrectAStoppedSession() async {
    let state = AppState()
    let gate = CaptureStopGate()
    state.isTranscribing = true
    state.audioCaptureService = RecoveryMicrophone(gate: gate)
    var armed = false
    let effects = CoreAudioCaptureRecoveryEffects(
      makeMicrophone: { _ in
        XCTFail("cancelled recovery cannot create a new driver")
        return RecoveryMicrophone()
      },
      armCapture: { _ in armed = true })
    let task = Task { await state.rebuildCoreAudioCaptureStack(reason: "silent", scope: .microphone, effects: effects) }
    await gate.waitUntilBlocked()
    state.isTranscribing = false
    state.audioCaptureService = nil
    await gate.unblock()
    let restarted = await task.value
    XCTAssertFalse(restarted)
    XCTAssertFalse(armed)
    XCTAssertNil(state.audioCaptureService)
  }

  func testTeardownCompletionCannotReplaceANewerMicrophoneOwner() async {
    let state = AppState()
    let gate = CaptureStopGate()
    state.isTranscribing = true
    state.audioCaptureService = RecoveryMicrophone(gate: gate)
    let newer = RecoveryMicrophone()
    let task = Task {
      await state.rebuildCoreAudioCaptureStack(
        reason: "silent", scope: .microphone, effects: effects(replacement: RecoveryMicrophone()))
    }
    await gate.waitUntilBlocked()
    state.audioCaptureService = newer
    await gate.unblock()
    let restarted = await task.value
    XCTAssertFalse(restarted)
    XCTAssertTrue(state.audioCaptureService === newer)
    XCTAssertTrue(newer.capturing)
  }

  func testDeferredMicrophoneRecoveryCannotDowngradePendingFullRecovery() async {
    let state = AppState()
    state.isTranscribing = true
    state.audioCaptureService = RecoveryMicrophone()
    state.captureGateInFlight = true
    await state.rebuildCoreAudioCaptureStack(reason: "silent", scope: .microphone)
    XCTAssertEqual(state.pendingCoreAudioCaptureRecovery?.scope, .microphone)
    await state.rebuildCoreAudioCaptureStack(reason: "rotation")
    await state.rebuildCoreAudioCaptureStack(reason: "silent", scope: .microphone)
    XCTAssertEqual(state.pendingCoreAudioCaptureRecovery?.scope, .allSources)
    XCTAssertEqual(state.pendingCoreAudioCaptureRecovery?.reason, "rotation")
    XCTAssertTrue(state.audioCaptureService?.capturing == true)
  }

  func testExhaustedMicrophoneLeavesLiveSystemAudioAndSessionRunning() async throws {
    guard #available(macOS 14.4, *) else { throw XCTSkip("Core Audio taps require macOS 14.4") }
    let state = AppState()
    let mic = RecoveryMicrophone()
    let tap = RecoverySystemAudio()
    state.isTranscribing = true
    state.currentSessionId = 42
    state.audioCaptureService = mic
    state.systemAudioCaptureService = tap
    state.silentMicRecoveryAttempts = 2
    let detection = AudioCaptureService.SilentMicDetection(
      deviceID: 7, deviceDescription: "test input", consecutiveSilentWindows: 2,
      isBluetoothTransport: false, framesReceived: 32000, peak: 0, secondsToFirstFrame: 0.1)

    await state.handleSharedCaptureSilentMicDetection(detection: detection, recordTrip: false)

    XCTAssertTrue(state.isTranscribing)
    XCTAssertEqual(state.currentSessionId, 42)
    XCTAssertTrue(mic.capturing)
    XCTAssertTrue(tap.capturing)
    XCTAssertTrue(state.isMicrophoneSignalMissing)
    XCTAssertEqual(CaptureListeningLogic.listeningStatus(appState: state), .blocked)
    let tooltip = ShellStatusTooltip.audio(
      state: .blocked, mode: "Always On", microphoneSignalMissing: true, systemAudioContinues: true)
    XCTAssertTrue(tooltip.contains("no microphone signal"))
    XCTAssertTrue(tooltip.contains("System audio is still recording"))
    XCTAssertFalse(tooltip.contains("transcription unavailable"))
    state.handleSharedMicrophoneSignalRecovered(from: mic)
    XCTAssertFalse(state.isMicrophoneSignalMissing)
    XCTAssertEqual(CaptureListeningLogic.listeningStatus(appState: state), .active)
  }

  func testStaleOrNeverStartedSystemAudioCannotCertifyContinuation() throws {
    guard #available(macOS 14.4, *) else { throw XCTSkip("Core Audio taps require macOS 14.4") }
    let state = AppState()
    state.systemAudioCaptureService = RecoverySystemAudio(live: false)
    XCTAssertFalse(state.isSystemAudioCaptureLive)
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 3, systemAudioLive: false), .stopAndSurfaceError)
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 3, systemAudioLive: true), .continueSystemAudio)
  }

  func testRetiredMicrophoneCannotClearCurrentOwnersMissingSignal() {
    let state = AppState()
    let current = RecoveryMicrophone()
    state.isTranscribing = true
    state.audioCaptureService = current
    state.isMicrophoneSignalMissing = true
    state.handleSharedMicrophoneSignalRecovered(from: RecoveryMicrophone())
    XCTAssertTrue(state.isMicrophoneSignalMissing)
    state.isTranscribing = false
    state.handleSharedMicrophoneSignalRecovered(from: current)
    XCTAssertTrue(state.isMicrophoneSignalMissing)
  }
}
