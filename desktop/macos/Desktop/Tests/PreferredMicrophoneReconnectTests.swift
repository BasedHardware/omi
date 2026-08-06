import CoreAudio
import XCTest

@testable import Omi_Computer

final class PreferredMicrophoneReconnectTests: XCTestCase {
  func testReappliesWhenPreferredResolvesOntoADifferentActiveDevice() {
    XCTAssertTrue(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7
      ))
  }

  func testDoesNotRestartWhenAlreadyPinnedToPreferred() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 42
      ))
  }

  func testDoesNotRestartWhenPreferredStillUnavailable() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: nil,
        activeCaptureDeviceID: 7
      ))
  }

  func testDoesNotRestartWithoutPreferredSelection() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: 7
      ))
  }

  func testDoesNotRestartBeforeCaptureHasAnActiveDevice() {
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: kAudioObjectUnknown
      ))
    XCTAssertFalse(
      PreferredMicrophoneReconnectPolicy.shouldReapplyPreferredMicrophone(
        preferredUID: "glasses-uid",
        resolvedPreferredDeviceID: 42,
        activeCaptureDeviceID: nil
      ))
  }

  func testAmbientTranscriptionWiresPreferredMicReconnectMonitor() throws {
    let transcriptionURL = sourcesRoot()
      .appendingPathComponent("AppState/AppState+Transcription.swift")
    let appStateURL = sourcesRoot().appendingPathComponent("AppState.swift")
    let monitorURL = sourcesRoot().appendingPathComponent("PreferredMicrophoneReconnect.swift")
    // omi-test-quality: source-inspection -- static contract: live transcription observes device reconnect
    let transcription = try String(contentsOf: transcriptionURL, encoding: .utf8)
    let appState = try String(contentsOf: appStateURL, encoding: .utf8)
    let monitor = try String(contentsOf: monitorURL, encoding: .utf8)

    XCTAssertTrue(appState.contains("preferredMicrophoneReconnectMonitor"))
    XCTAssertTrue(transcription.contains("preferredMicrophoneReconnectMonitor.start(observing: self)"))
    XCTAssertTrue(transcription.contains("preferredMicrophoneReconnectMonitor.stop()"))
    XCTAssertTrue(monitor.contains("kAudioHardwarePropertyDevices"))
    XCTAssertTrue(monitor.contains("prepareTranscriptionRestartAfterSettingsChange"))
  }

  private func sourcesRoot() -> URL {
    URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
  }
}
