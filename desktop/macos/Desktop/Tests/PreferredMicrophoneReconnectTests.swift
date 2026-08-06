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

  @MainActor
  func testMonitorStopIsIdempotentWithoutStart() {
    let monitor = PreferredMicrophoneReconnectMonitor()
    monitor.stop()
    monitor.stop()
  }
}
