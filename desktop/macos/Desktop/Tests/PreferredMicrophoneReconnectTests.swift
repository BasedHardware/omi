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

  func testAmbientTranscriptionWiresPreferredMicReconnectMonitor() throws {
    let transcriptionURL = sourcesRoot()
      .appendingPathComponent("AppState/AppState+Transcription.swift")
    let appStateURL = sourcesRoot().appendingPathComponent("AppState.swift")
    let monitorURL = sourcesRoot()
      .appendingPathComponent("Audio/PreferredMicrophoneReconnect.swift")
    // omi-test-quality: source-inspection -- static contract: live transcription observes device reconnect
    let transcription = try String(contentsOf: transcriptionURL, encoding: .utf8)
    let appState = try String(contentsOf: appStateURL, encoding: .utf8)
    let monitor = try String(contentsOf: monitorURL, encoding: .utf8)

    XCTAssertTrue(appState.contains("preferredMicrophoneReconnectMonitor"))
    XCTAssertTrue(appState.contains("preferredMicrophoneReconnectMonitor.start(observing: self)"))
    XCTAssertTrue(appState.contains("didSet"))
    XCTAssertTrue(transcription.contains("preferredMicrophoneReconnectMonitor.stop()"))
    XCTAssertTrue(monitor.contains("kAudioHardwarePropertyDevices"))
    XCTAssertTrue(monitor.contains("prepareTranscriptionRestartAfterSettingsChange"))
    XCTAssertTrue(monitor.contains("isCaptureLive"))
    XCTAssertTrue(monitor.contains("capturing"))
  }

  private func sourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }
}
