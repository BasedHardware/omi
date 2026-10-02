import CoreAudio
import XCTest

@testable import Omi_Computer

/// SCA-526 regression coverage: the ambient stop/restart loop split one
/// conversation into many on stable 12371. These tests pin the three
/// contracts that broke: rotations must serialize (`.busy`, not `.error`),
/// a preferred-mic reconnect must swap capture in place instead of tearing
/// the session down, and a second terminalization must not re-emit
/// `Desktop Recording Stopped`.
private final class FakeCapturingService: AudioCaptureService, @unchecked Sendable {
  private let lock = NSLock()
  private var stopped = false
  var fakeDeviceID: AudioDeviceID
  var fakeCapturing: Bool

  init(deviceID: AudioDeviceID, capturing: Bool = true) {
    fakeDeviceID = deviceID
    fakeCapturing = capturing
    super.init()
  }

  override var capturing: Bool { fakeCapturing }
  override var activeDeviceID: AudioDeviceID { fakeDeviceID }
  override func stopCapture() {
    lock.withLock { stopped = true }
  }

  var didStop: Bool { lock.withLock { stopped } }
}

@MainActor
final class RecordingStopRestartLoopTests: XCTestCase {
  // MARK: - Rotation serialization

  func testFinishConversationCoalescesWhileRotationInFlight() async {
    let state = AppState()
    state.isTranscribing = true
    state.conversationRotationInFlight = true

    let result = await state.finishConversation()

    guard case .busy = result else {
      XCTFail("expected .busy while another rotation owns the session, got \(result)")
      return
    }
  }

  func testFinishConversationStillErrorsWhenSessionStopped() async {
    let state = AppState()
    state.isTranscribing = false

    let result = await state.finishConversation()

    guard case .error = result else {
      XCTFail("expected .error when transcription is inactive, got \(result)")
      return
    }
  }

  // MARK: - Double-stop suppression

  func testStopTranscriptionReturnsNilWhenAlreadyStopped() {
    let state = AppState()
    state.isTranscribing = false

    XCTAssertNil(
      state.stopTranscription(finalizationReason: .rotationFailed),
      "A second terminalization must not re-emit Desktop Recording Stopped")
  }

  // MARK: - Preferred-mic in-place swap

  func testPreferredMicSwapPreservesSessionAndAttemptIdentity() {
    let state = AppState()
    let capture = FakeCapturingService(deviceID: 7)
    state.isTranscribing = true
    state.audioCaptureService = capture
    state.currentSessionId = 42
    let attempt = CaptureAttemptOutcomeState(mode: "always", intent: .userStart)
    state.captureAttempt = attempt

    XCTAssertTrue(
      state.swapCaptureServiceToPreferredMicrophone(deviceID: 42, deviceName: "Glasses"))

    XCTAssertTrue(capture.didStop, "the old capture service must be stopped")
    XCTAssertTrue(
      state.audioCaptureService !== capture, "a replacement service must be installed")
    XCTAssertTrue(
      state.audioCaptureService?.hasOverrideDevice == true,
      "the replacement must be pinned to the preferred device")
    XCTAssertTrue(state.isTranscribing, "the session must survive the swap")
    XCTAssertEqual(
      state.currentSessionId, 42, "the session id must survive the swap")
    XCTAssertEqual(
      state.captureAttempt?.attemptId, attempt.attemptId,
      "the capture attempt identity must survive the swap — a full restart would mint a new one")
    XCTAssertNotNil(state.lastPreferredMicSwapAt, "the swap cooldown anchor must be set")
  }

  func testPreferredMicSwapRefusesHealedSilentDevice() {
    let state = AppState()
    let capture = FakeCapturingService(deviceID: 7)
    state.isTranscribing = true
    state.audioCaptureService = capture
    state.silentMicHealedDeviceID = 42

    XCTAssertFalse(
      state.swapCaptureServiceToPreferredMicrophone(deviceID: 42, deviceName: "Glasses"))
    XCTAssertFalse(capture.didStop)
    XCTAssertTrue(state.audioCaptureService === capture)
  }

  func testPreferredMicSwapRefusesSameDeviceAndStoppedCapture() {
    let state = AppState()
    let capture = FakeCapturingService(deviceID: 42)
    state.isTranscribing = true
    state.audioCaptureService = capture

    XCTAssertFalse(
      state.swapCaptureServiceToPreferredMicrophone(deviceID: 42, deviceName: nil))

    let idle = FakeCapturingService(deviceID: 7, capturing: false)
    state.audioCaptureService = idle
    XCTAssertFalse(
      state.swapCaptureServiceToPreferredMicrophone(deviceID: 42, deviceName: nil))
    XCTAssertFalse(idle.didStop)
  }

  func testPreferredMicReapplyDefersWhileCaptureGateInFlight() async {
    let state = AppState()
    let capture = FakeCapturingService(deviceID: 7)
    state.isTranscribing = true
    state.audioCaptureService = capture
    state.captureGateInFlight = true

    await state.reapplyPreferredMicrophone(deviceID: 42, deviceName: "Glasses")

    XCTAssertEqual(state.pendingPreferredMicReapplyDeviceID, 42)
    XCTAssertEqual(state.pendingPreferredMicReapplyDeviceName, "Glasses")
    XCTAssertFalse(capture.didStop, "no swap may run while the gate is mid-flight")
    XCTAssertTrue(state.audioCaptureService === capture)
  }

  // MARK: - Paywall admission debounce

  func testPaywallAdmissionStopCannotBeClearedInsideDebounceWindow() {
    let now = Date()
    let admission = now.addingTimeInterval(-60)

    XCTAssertFalse(
      AppState.mayClearPaywallFlag(lastAdmissionStopAt: admission, now: now),
      "a 60s-old admission stop must hold against the trial-metadata poll")
    XCTAssertTrue(
      AppState.mayClearPaywallFlag(
        lastAdmissionStopAt: now.addingTimeInterval(
          -AppState.paywallAdmissionClearDebounce),
        now: now),
      "a genuinely reactivated plan must still self-heal after the debounce")
    XCTAssertTrue(
      AppState.mayClearPaywallFlag(lastAdmissionStopAt: nil, now: now),
      "no admission stop on record means the metadata poll is authoritative")
  }
}
