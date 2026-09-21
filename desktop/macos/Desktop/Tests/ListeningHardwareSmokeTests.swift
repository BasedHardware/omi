import XCTest

@testable import Omi_Computer

/// On-device smoke: mic + BLE stay up across the transcription gate.
/// Requires a real microphone and a paired/discoverable Omi on this Mac.
/// NOT executed in CI or this sandbox — skipped unless `OMI_HARDWARE_SMOKE=1`.
///
/// Run:
/// `OMI_HARDWARE_SMOKE=1 xcrun swift test --package-path desktop/macos/Desktop --filter ListeningHardwareSmokeTests`
final class ListeningHardwareSmokeTests: XCTestCase {
  static let liveEnvironmentKey = "OMI_HARDWARE_SMOKE"

  @MainActor
  func testMicAndBleStayUpAcrossTranscriptionGate_requiresHardware() async throws {
    try XCTSkipUnless(
      ProcessInfo.processInfo.environment[Self.liveEnvironmentKey] == "1",
      "hardware smoke skipped unless OMI_HARDWARE_SMOKE=1; needs a real mic + BLE device. Not executed here."
    )
    try XCTSkipUnless(
      AudioCaptureService.checkPermission(),
      "hardware smoke needs microphone permission for this test runner")

    let previousMode = AssistantSettings.shared.audioRecordingMode
    let mic = AudioCaptureService()
    defer {
      AssistantSettings.shared.audioRecordingMode = previousMode
      mic.stopCapture()
      BleAudioService.shared.stopProcessing()
    }
    AssistantSettings.shared.audioRecordingMode = .always
    try await mic.startCapture(onAudioChunk: { _ in }, onAudioLevel: nil)
    XCTAssertTrue(mic.capturing, "real mic capture must start before the gate")

    let provider = DeviceProvider.shared
    if provider.activeConnection == nil, let paired = provider.pairedDevice {
      await provider.connect(to: paired)
    }
    if provider.activeConnection == nil {
      provider.startDiscovery(timeout: 8)
      for _ in 0..<80 where provider.activeConnection == nil {
        if let device = provider.discoveredDevices.first {
          await provider.connect(to: device)
          break
        }
        try await Task.sleep(for: .milliseconds(100))
      }
    }
    guard let connection = provider.activeConnection else {
      throw XCTSkip(
        "hardware smoke needs a live BLE connection (pair an Omi, then re-run with OMI_HARDWARE_SMOKE=1)")
    }
    let bleConnectedBeforeGate = await connection.isConnected()
    try XCTSkipUnless(
      bleConnectedBeforeGate,
      "hardware smoke needs the BLE connection to report connected")

    if !BleAudioService.shared.isProcessing {
      await BleAudioService.shared.startProcessing(from: connection)
    }
    XCTAssertTrue(BleAudioService.shared.isProcessing)
    XCTAssertTrue(BleAudioService.shared.processingConnection === connection)
    let bleGeneration = BleAudioService.shared.processingGeneration

    let appState = AppState()
    appState.audioCaptureService = mic
    appState.audioSource = .bleDevice
    appState.isTranscribing = true

    appState.setTranscriptionPaused(true, source: "hardware-smoke")
    XCTAssertTrue(mic.capturing, "mic must stay up while transcription is gated")
    XCTAssertTrue(BleAudioService.shared.isProcessing, "BLE processing must stay up while gated")
    XCTAssertTrue(BleAudioService.shared.processingConnection === connection)
    let bleConnectedWhileGated = await connection.isConnected()
    XCTAssertTrue(bleConnectedWhileGated)
    XCTAssertEqual(BleAudioService.shared.processingGeneration, bleGeneration)

    appState.setTranscriptionPaused(false, source: "hardware-smoke")
    XCTAssertTrue(mic.capturing, "resume must not tear down or restart mic")
    XCTAssertTrue(BleAudioService.shared.isProcessing, "resume must not tear down or restart BLE")
    XCTAssertTrue(BleAudioService.shared.processingConnection === connection)
    let bleConnectedAfterResume = await connection.isConnected()
    XCTAssertTrue(bleConnectedAfterResume)
    XCTAssertEqual(BleAudioService.shared.processingGeneration, bleGeneration)
    XCTAssertTrue(appState.audioCaptureService === mic)
  }
}
