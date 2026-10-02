import CoreAudio
import XCTest

@testable import Omi_Computer

final class PreferredMicrophoneReconnectTests: XCTestCase {
  func testReappliesWhenPreferredResolvesOntoADifferentActiveDevice() {
    XCTAssertTrue(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: true
      ))
  }

  func testDoesNotRestartWhenAlreadyPinnedToPreferred() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 42,
        isCaptureLive: true
      ))
  }

  func testDoesNotRestartWhenPreferredStillUnavailable() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: nil,
        activeCaptureDeviceID: 7,
        isCaptureLive: true
      ))
  }

  func testDoesNotRestartWithoutPreferredSelection() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: true
      ))
  }

  func testDoesNotRestartBeforeCaptureHasAnActiveDevice() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: kAudioObjectUnknown,
        isCaptureLive: true
      ))
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: nil,
        isCaptureLive: true
      ))
  }

  func testDoesNotRestartWhileCaptureIsStartingOrStopped() {
    // deviceID can be assigned before isCapturing flips true during HAL startup.
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: false
      ))
  }

  // MARK: - SCA-526: device-list flap must not loop capture swaps

  func testDoesNotReapplyInsideSwapCooldown() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: true,
        secondsSinceLastSwap: PreferredMicrophoneReconnectPolicy.swapCooldown - 1
      ))
  }

  func testReappliesOnceSwapCooldownElapses() {
    XCTAssertTrue(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: true,
        secondsSinceLastSwap: PreferredMicrophoneReconnectPolicy.swapCooldown
      ))
  }

  func testDoesNotReapplyOntoDeviceHealedAsSilent() {
    // The silent-mic watchdog already proved this device dead this session;
    // re-pinning onto it would undo the heal and ping-pong with the watchdog.
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: true,
        healedCaptureDeviceID: 42
      ))
  }

  func testHealedDeviceDoesNotBlockOtherResolvedDevice() {
    XCTAssertTrue(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7,
        isCaptureLive: true,
        healedCaptureDeviceID: 99
      ))
  }

  @MainActor
  func testMonitorStopIsIdempotentWithoutStart() {
    let monitor = PreferredMicrophoneReconnectMonitor()
    monitor.stop()
    monitor.stop()
  }
}
