import Foundation
import XCTest

@testable import Omi_Computer

final class SilentMicDiagnosticTelemetryTests: XCTestCase {
  func testExactDiagnosticAndArmedPayloadKeys() {
    let snapshot = SilentMicDiagnosticTelemetry.Snapshot(
      attemptID: "opaque", recoveryAttempt: 2, phase: "rebuild", result: "watchdog_trip",
      launchContext: "update_relaunch", updateAttemptID: "update-opaque",
      secondsSinceLaunch: "10_30s", secondsSinceWake: "unknown",
      secondsSinceUnlock: "unknown",
      presence: CapturePresence(
        screenLocked: true, displaysAsleep: false,
        consoleSessionActive: true, lidClosed: false, appActive: false),
      transport: "bluetooth", isSystemDefault: true, healedRouteOverride: false,
      deviceIsAlive: true, deviceIsRunningSomewhere: false, hogModePIDPresent: false,
      nominalSampleRate: "32_48k", channelCount: "1", inputDeviceCount: "2_9",
      defaultInputChangedSinceLaunch: false, framesReceived: "100_plus",
      signalClass: "all_zero", peak: "zero", timeToFirstFrame: "0_10s",
      micAuthorization: "authorized")
    let properties = SilentMicDiagnosticTelemetry.properties(snapshot)
    XCTAssertEqual(SilentMicDiagnosticTelemetry.eventName, "Desktop Silent Mic Diagnostic")
    XCTAssertEqual(
      Set(properties.keys),
      [
        "platform", "attempt_id", "recovery_attempt", "phase", "result", "launch_context",
        "update_attempt_id", "seconds_since_launch", "seconds_since_wake", "seconds_since_unlock",
        "screen_locked", "displays_asleep", "console_session_active", "lid_closed", "app_active",
        "input_transport", "input_is_system_default", "healed_route_override", "device_is_alive",
        "device_is_running_somewhere", "hog_mode_pid_present", "nominal_sample_rate",
        "channel_count", "input_device_count", "default_input_changed_since_launch",
        "frames_received", "signal_class", "peak", "time_to_first_frame", "mic_authorization",
      ])
    XCTAssertEqual(properties["screen_locked"] as? String, "true")
    XCTAssertEqual(properties["input_transport"] as? String, "bluetooth")
    XCTAssertEqual(properties["update_attempt_id"] as? String, "update-opaque")

    let armed = SilentMicDiagnosticTelemetry.armedProperties(
      attemptID: "episode", phase: "recovered", trigger: "unlock",
      launchContext: "update_relaunch", updateAttemptID: "update-opaque", duration: "1_5m")
    XCTAssertEqual(SilentMicDiagnosticTelemetry.armedEventName, "Desktop Microphone Armed")
    XCTAssertEqual(
      Set(armed.keys),
      [
        "platform", "attempt_id", "phase", "trigger",
        "launch_context", "update_attempt_id", "armed_duration", "flap_count", "continued_episode",
      ])
    XCTAssertEqual(armed["flap_count"] as? String, "0")
    XCTAssertEqual(armed["continued_episode"] as? Bool, false)
    let continued = SilentMicDiagnosticTelemetry.armedProperties(
      attemptID: "episode", phase: "retry", trigger: "backoff",
      launchContext: "other", updateAttemptID: nil, duration: "1_5m",
      flapCount: 3, continuedEpisode: true)
    XCTAssertEqual(continued["flap_count"] as? String, "2_9")
    XCTAssertEqual(continued["continued_episode"] as? Bool, true)
    let skipped = SilentMicDiagnosticTelemetry.armedProperties(
      attemptID: "episode", phase: "retry_skipped", trigger: "backoff",
      launchContext: "update_relaunch", updateAttemptID: "update-opaque", duration: "5_60m",
      presenceReason: "screen_locked")
    XCTAssertEqual(skipped["phase"] as? String, "retry_skipped")
    XCTAssertEqual(skipped["presence_reason"] as? String, "screen_locked")
    XCTAssertEqual(Set(skipped.keys), Set(armed.keys).union(["presence_reason"]))
  }

  func testDiagnosticRateCapPerAttemptAndPerHour() {
    var cap = SilentMicDiagnosticRateLimit()
    let start = Date(timeIntervalSince1970: 1_000)
    for _ in 0..<6 { XCTAssertTrue(cap.allow(attemptID: "same", now: start)) }
    XCTAssertFalse(cap.allow(attemptID: "same", now: start))
    for index in 0..<18 { XCTAssertTrue(cap.allow(attemptID: "a\(index)", now: start)) }
    XCTAssertFalse(cap.allow(attemptID: "overflow", now: start))
    XCTAssertTrue(cap.allow(attemptID: "same", now: start.addingTimeInterval(3_600)))
  }

  func testSilentPCMIsNeverSentToCloudSink() {
    let zero = Data(repeating: 0, count: 64)
    let belowThreshold = Data([1, 0, 5, 0, 251, 255])
    let live = Data([6, 0])
    var sent = 0
    for chunk in [zero, belowThreshold, live] {
      if AudioCaptureService.containsLivePCM(chunk) { sent += 1 }
    }
    XCTAssertEqual(sent, 1)
  }
}
