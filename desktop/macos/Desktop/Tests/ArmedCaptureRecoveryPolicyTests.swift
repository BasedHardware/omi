import Foundation
import XCTest

@testable import Omi_Computer

final class ArmedCaptureRecoveryPolicyTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1_000)

  func testAutomaticExhaustionReleasesResourcesAndKeepsIntent() {
    var policy = ArmedCaptureRecoveryPolicy()
    var resources = (mic: true, coreAudio: true, stt: true, intent: true)
    let action = policy.enter(now: start)
    if case .releaseAndWait = action {
      resources.mic = false
      resources.coreAudio = false
      resources.stt = false
    } else {
      XCTFail("automatic exhaustion must release the capture stack")
    }
    XCTAssertEqual(policy.state, .waiting)
    XCTAssertFalse(resources.mic)
    XCTAssertFalse(resources.coreAudio)
    XCTAssertFalse(resources.stt)
    XCTAssertTrue(resources.intent)
    XCTAssertTrue(
      ArmedCaptureRecoveryPolicy.canEnterWaiting(
        captureActive: resources.mic || resources.coreAudio, sttActive: resources.stt))
    XCTAssertFalse(
      ArmedCaptureRecoveryPolicy.canEnterWaiting(
        captureActive: false, sttActive: true))
    XCTAssertTrue(
      ArmedCaptureRecoveryPolicy.shouldDeferStart(
        transitionInFlight: true, userInitiated: false))
    XCTAssertFalse(
      ArmedCaptureRecoveryPolicy.shouldDeferStart(
        transitionInFlight: true, userInitiated: true))
  }

  func testProbeGateBlocksAllProviderAudioUntilLiveMicrophoneFrame() {
    let gate = CaptureProbeAudioGate()
    var sent = 0
    let liveSystemAudio = Data([10, 0])
    gate.setOpen(false)
    if gate.isOpen && AudioCaptureService.containsLivePCM(liveSystemAudio) { sent += 1 }
    XCTAssertEqual(sent, 0)
    gate.setOpen(true)
    if gate.isOpen && AudioCaptureService.containsLivePCM(liveSystemAudio) { sent += 1 }
    XCTAssertEqual(sent, 1)
  }

  func testBackoffScheduleThenTenMinuteCeiling() {
    var policy = ArmedCaptureRecoveryPolicy()
    for (index, delay) in [30.0, 60, 120, 300, 600, 600].enumerated() {
      let now = start.addingTimeInterval(Double(index) * 1_000)
      XCTAssertEqual(policy.enter(now: now), .releaseAndWait(until: now.addingTimeInterval(delay)))
      XCTAssertEqual(policy.signal(.backoff, now: now.addingTimeInterval(delay - 1)), .none)
      XCTAssertEqual(policy.signal(.backoff, now: now.addingTimeInterval(delay)), .probe)
    }
  }

  func testEveryRepairSignalStartsAnImmediateSingleProbe() {
    for signal in [
      ArmedCaptureRecoveryPolicy.Signal.unlock, .screenWake, .systemWake,
      .sessionActive, .inputChanged, .displayChanged, .appActive,
    ] {
      var policy = ArmedCaptureRecoveryPolicy()
      _ = policy.enter(now: start)
      XCTAssertEqual(policy.signal(signal, now: start.addingTimeInterval(1)), .probe)
      XCTAssertEqual(policy.signal(signal, now: start.addingTimeInterval(2)), .none)
      XCTAssertEqual(policy.state, .probing)
    }
  }

  func testLiveProbeResumesAndNextAttemptGetsFreshIdentity() {
    var policy = ArmedCaptureRecoveryPolicy()
    _ = policy.enter(now: start)
    XCTAssertEqual(policy.signal(.unlock, now: start.addingTimeInterval(5)), .probe)
    XCTAssertEqual(policy.succeeded(now: start.addingTimeInterval(7)), 7)
    XCTAssertEqual(policy.state, .idle)
    let first = CaptureAttemptOutcomeState(mode: "always", intent: .auto)
    let second = CaptureAttemptOutcomeState(mode: "always", intent: .auto)
    XCTAssertNotEqual(first.attemptId, second.attemptId)
  }

  func testUpdateRelaunchPresenceGate() {
    XCTAssertTrue(
      ArmedCaptureRecoveryPolicy.shouldWaitForUpdateRelaunch(
        isUpdateRelaunch: true, consoleActive: true, screenLocked: true, displaysAsleep: false))
    XCTAssertTrue(
      ArmedCaptureRecoveryPolicy.shouldWaitForUpdateRelaunch(
        isUpdateRelaunch: true, consoleActive: true, screenLocked: false, displaysAsleep: true))
    XCTAssertTrue(
      ArmedCaptureRecoveryPolicy.shouldWaitForUpdateRelaunch(
        isUpdateRelaunch: true, consoleActive: false, screenLocked: false, displaysAsleep: false))
    XCTAssertFalse(
      ArmedCaptureRecoveryPolicy.shouldWaitForUpdateRelaunch(
        isUpdateRelaunch: true, consoleActive: true, screenLocked: false, displaysAsleep: false))
    XCTAssertFalse(
      ArmedCaptureRecoveryPolicy.shouldWaitForUpdateRelaunch(
        isUpdateRelaunch: false, consoleActive: false, screenLocked: true, displaysAsleep: true))
  }

  func testManualAndPermissionPoliciesRemainTerminal() {
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 3), .stopAndSurfaceError)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .denied, userInitiated: false),
      .abandonAutomaticStart)
    XCTAssertEqual(MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .denied), .permission)
  }
}
