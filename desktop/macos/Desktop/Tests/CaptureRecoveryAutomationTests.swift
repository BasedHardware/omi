import XCTest

@testable import Omi_Computer

@MainActor
final class CaptureRecoveryAutomationTests: XCTestCase {
  func testReadOnlySnapshotAndFaultInjectionDeclareDistinctEffects() async throws {
    let registry = DesktopAutomationActionRegistry()
    registry.registerCaptureRecoveryActions()
    let observation = try XCTUnwrap(registry.descriptors().first { $0.name == "capture_source_recovery_snapshot" })
    XCTAssertTrue(observation.effects.isEmpty)
    let injection = try XCTUnwrap(registry.descriptors().first { $0.name == "inject_silent_microphone_trip" })
    XCTAssertTrue(injection.effects.contains(.localState))
    XCTAssertTrue(injection.effects.contains(.remoteWrite))
    do {
      _ = try await registry.perform("inject_silent_microphone_trip", params: [:], readOnly: true)
      XCTFail("fault injection cannot be dispatched as observation-only")
    } catch DesktopAutomationActionError.requiresEffects(let name) {
      XCTAssertEqual(name, "inject_silent_microphone_trip")
    }
  }

  func testFaultInjectionCannotArmCaptureOutsideSyntheticLocalProfile() async throws {
    let registry = DesktopAutomationActionRegistry()
    registry.registerCaptureRecoveryActions()
    let result = try await registry.perform("inject_silent_microphone_trip", params: [:])
    XCTAssertEqual(result?["error"], "requires a non-production local harness profile")
  }

  func testSnapshotReportsMissingSignalWithoutRecordingContentOrIdentity() {
    let state = AppState()
    state.isTranscribing = true
    state.isMicrophoneSignalMissing = true
    let snapshot = state.captureSourceRecoverySnapshot()
    XCTAssertEqual(snapshot["microphone_signal_missing"], "true")
    XCTAssertEqual(snapshot["system_audio_live"], "false")
    XCTAssertTrue(snapshot["listening_tooltip"]?.contains("no microphone signal") == true)
    XCTAssertFalse(snapshot["listening_tooltip"]?.contains("still recording") == true)
    XCTAssertEqual(
      Set(snapshot.keys),
      [
        "is_transcribing", "is_live_capturing", "microphone_capturing", "microphone_signal_missing",
        "system_audio_live", "recovery_attempts", "capture_gate_in_flight", "has_transcription_error",
        "listening_tooltip",
      ])
  }
}
