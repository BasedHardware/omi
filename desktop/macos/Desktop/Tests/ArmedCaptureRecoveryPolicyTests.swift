import Foundation
import XCTest

@testable import Omi_Computer

final class ArmedCaptureRecoveryPolicyTests: XCTestCase {
  private let start = Date(timeIntervalSince1970: 1_000)
  private let present = CapturePresence(
    screenLocked: false, displaysAsleep: false,
    consoleSessionActive: true, lidClosed: false, appActive: false)

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
      XCTAssertEqual(
        policy.signal(.backoff, now: now.addingTimeInterval(delay - 1), presence: present, inputIsBuiltIn: nil), .none)
      XCTAssertEqual(
        policy.signal(.backoff, now: now.addingTimeInterval(delay), presence: present, inputIsBuiltIn: nil), .probe)
    }
  }

  func testEveryRepairSignalStartsAnImmediateSingleProbe() {
    for signal in [
      ArmedCaptureRecoveryPolicy.Signal.unlock, .screenWake, .systemWake,
      .sessionActive, .inputChanged, .displayChanged, .appActive,
    ] {
      var policy = ArmedCaptureRecoveryPolicy()
      _ = policy.enter(now: start)
      XCTAssertEqual(
        policy.signal(signal, now: start.addingTimeInterval(1), presence: present, inputIsBuiltIn: nil), .probe)
      XCTAssertEqual(
        policy.signal(signal, now: start.addingTimeInterval(2), presence: present, inputIsBuiltIn: nil), .none)
      XCTAssertEqual(policy.state, .probing)
    }
  }

  func testLiveProbeResumesAndNextAttemptGetsFreshIdentity() {
    var policy = ArmedCaptureRecoveryPolicy()
    _ = policy.enter(now: start)
    XCTAssertEqual(
      policy.signal(.unlock, now: start.addingTimeInterval(5), presence: present, inputIsBuiltIn: nil), .probe)
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

  func testAbsentPresenceSkipsBackoffAndBlocksAllRepairSignals() {
    let absent: [(CapturePresence, Bool?, ArmedCaptureRecoveryPolicy.PresenceReason)] = [
      (
        CapturePresence(
          screenLocked: false, displaysAsleep: false, consoleSessionActive: false, lidClosed: false, appActive: false),
        nil, .consoleInactive
      ),
      (
        CapturePresence(
          screenLocked: true, displaysAsleep: false, consoleSessionActive: true, lidClosed: false, appActive: false),
        nil, .screenLocked
      ),
      (
        CapturePresence(
          screenLocked: false, displaysAsleep: true, consoleSessionActive: true, lidClosed: false, appActive: false),
        nil, .displaysAsleep
      ),
      (
        CapturePresence(
          screenLocked: false, displaysAsleep: false, consoleSessionActive: true, lidClosed: true, appActive: false),
        true, .lidClosedBuiltIn
      ),
    ]
    for (presence, builtIn, reason) in absent {
      var policy = ArmedCaptureRecoveryPolicy()
      _ = policy.enter(now: start)
      XCTAssertEqual(
        policy.signal(.backoff, now: start.addingTimeInterval(30), presence: presence, inputIsBuiltIn: builtIn),
        .retrySkipped(reason: reason, until: start.addingTimeInterval(60)))
      XCTAssertEqual(policy.state, .waiting)
      XCTAssertEqual(policy.retryCount, 1)
      for signal in [
        ArmedCaptureRecoveryPolicy.Signal.unlock, .screenWake, .systemWake, .sessionActive,
        .inputChanged, .displayChanged, .appActive,
      ] {
        XCTAssertEqual(
          policy.signal(signal, now: start.addingTimeInterval(31), presence: presence, inputIsBuiltIn: builtIn), .none)
      }
      XCTAssertEqual(
        policy.signal(.backoff, now: start.addingTimeInterval(60), presence: present, inputIsBuiltIn: nil), .probe)
    }
  }

  func testSkippedBackoffsKeepIntervalUntilAnActualProbeFails() {
    var policy = ArmedCaptureRecoveryPolicy()
    let locked = CapturePresence(
      screenLocked: true, displaysAsleep: true, consoleSessionActive: true,
      lidClosed: false, appActive: false)
    _ = policy.enter(now: start)
    for second in [30.0, 60, 90] {
      XCTAssertEqual(
        policy.signal(.backoff, now: start.addingTimeInterval(second), presence: locked, inputIsBuiltIn: nil),
        .retrySkipped(reason: .screenLocked, until: start.addingTimeInterval(second + 30)))
      XCTAssertEqual(policy.retryCount, 1)
    }
    XCTAssertEqual(
      policy.signal(.unlock, now: start.addingTimeInterval(91), presence: present, inputIsBuiltIn: nil), .probe)
    XCTAssertEqual(
      policy.enter(now: start.addingTimeInterval(100)), .releaseAndWait(until: start.addingTimeInterval(160)))
    XCTAssertEqual(policy.retryCount, 2)
    XCTAssertEqual(policy.enteredAt, start)
  }

  func testUnknownPresenceSkipsOnlyTimerAndExternalInputCanProbeWithClosedLid() {
    let unknown = CapturePresence(
      screenLocked: nil, displaysAsleep: false, consoleSessionActive: true,
      lidClosed: nil, appActive: false)
    var policy = ArmedCaptureRecoveryPolicy()
    _ = policy.enter(now: start)
    XCTAssertEqual(
      policy.signal(.backoff, now: start.addingTimeInterval(30), presence: unknown, inputIsBuiltIn: nil),
      .retrySkipped(reason: .unknown, until: start.addingTimeInterval(60)))
    XCTAssertEqual(
      policy.signal(.appActive, now: start.addingTimeInterval(31), presence: unknown, inputIsBuiltIn: nil), .probe)

    let unknownLid = CapturePresence(
      screenLocked: false, displaysAsleep: false, consoleSessionActive: true,
      lidClosed: nil, appActive: true)
    var lidPolicy = ArmedCaptureRecoveryPolicy()
    _ = lidPolicy.enter(now: start)
    XCTAssertEqual(
      lidPolicy.signal(.backoff, now: start.addingTimeInterval(30), presence: unknownLid, inputIsBuiltIn: nil),
      .retrySkipped(reason: .unknown, until: start.addingTimeInterval(60)))
    XCTAssertEqual(
      lidPolicy.signal(.displayChanged, now: start.addingTimeInterval(31), presence: unknownLid, inputIsBuiltIn: nil),
      .probe)

    let clamshell = CapturePresence(
      screenLocked: false, displaysAsleep: false, consoleSessionActive: true,
      lidClosed: true, appActive: false)
    var external = ArmedCaptureRecoveryPolicy()
    _ = external.enter(now: start)
    XCTAssertEqual(
      external.signal(.backoff, now: start.addingTimeInterval(30), presence: clamshell, inputIsBuiltIn: false), .probe)
    var uncertain = ArmedCaptureRecoveryPolicy()
    _ = uncertain.enter(now: start)
    XCTAssertEqual(
      uncertain.signal(.backoff, now: start.addingTimeInterval(30), presence: clamshell, inputIsBuiltIn: nil),
      .retrySkipped(reason: .unknown, until: start.addingTimeInterval(60)))
    XCTAssertEqual(
      uncertain.signal(.inputChanged, now: start.addingTimeInterval(31), presence: clamshell, inputIsBuiltIn: nil),
      .probe)
  }

  func testMissingScreenLockFactRemainsUnknown() {
    XCTAssertNil(CapturePresence.screenLockState(from: nil))
    XCTAssertNil(CapturePresence.screenLockState(from: [:]))
    XCTAssertEqual(CapturePresence.screenLockState(from: ["CGSSessionScreenIsLocked": true]), true)
    XCTAssertEqual(CapturePresence.screenLockState(from: ["CGSSessionScreenIsLocked": false]), false)
  }

  func testManualAndPermissionPoliciesRemainTerminal() {
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 3), .stopAndSurfaceError)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .denied, userInitiated: false),
      .abandonAutomaticStart)
    XCTAssertEqual(MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .denied), .permission)
  }
}
