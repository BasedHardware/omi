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
    var forwarded: [Data] = []
    let chunks = [Data(repeating: 0, count: 64), Data([1, 0]), Data([10, 0])]
    gate.setOpen(false)
    for chunk in chunks { gate.forward(chunk) { forwarded.append($0) } }
    XCTAssertTrue(forwarded.isEmpty)
    gate.setOpen(true)
    for chunk in chunks { gate.forward(chunk) { forwarded.append($0) } }
    XCTAssertEqual(forwarded, chunks, "open capture forwards every chunk, including silence")
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

  func testSkippedBackoffsEscalateWithoutConsumingRetryCount() {
    var policy = ArmedCaptureRecoveryPolicy()
    let locked = CapturePresence(
      screenLocked: true, displaysAsleep: true, consoleSessionActive: true,
      lidClosed: false, appActive: false)
    _ = policy.enter(now: start)
    for (second, nextDelay) in [(30.0, 30.0), (60, 60), (120, 120)] {
      XCTAssertEqual(
        policy.signal(.backoff, now: start.addingTimeInterval(second), presence: locked, inputIsBuiltIn: nil),
        .retrySkipped(reason: .screenLocked, until: start.addingTimeInterval(second + nextDelay)))
      XCTAssertEqual(policy.retryCount, 1)
    }
    XCTAssertEqual(
      policy.signal(.unlock, now: start.addingTimeInterval(241), presence: present, inputIsBuiltIn: nil), .probe)
    XCTAssertEqual(
      policy.enter(now: start.addingTimeInterval(250)), .releaseAndWait(until: start.addingTimeInterval(310)))
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
      lidPolicy.signal(.backoff, now: start.addingTimeInterval(30), presence: unknownLid, inputIsBuiltIn: nil), .probe)
    XCTAssertEqual(
      lidPolicy.signal(.displayChanged, now: start.addingTimeInterval(31), presence: unknownLid, inputIsBuiltIn: nil),
      .none)

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

  func testScreenLockStateDistinguishesMissingDictionaryFromMissingKey() {
    XCTAssertNil(CapturePresence.screenLockState(from: nil))
    XCTAssertEqual(CapturePresence.screenLockState(from: [:]), false)
    XCTAssertEqual(CapturePresence.screenLockState(from: ["CGSSessionScreenIsLocked": true]), true)
    XCTAssertEqual(CapturePresence.screenLockState(from: ["CGSSessionScreenIsLocked": false]), false)
    XCTAssertNil(CapturePresence.screenLockState(from: ["CGSSessionScreenIsLocked": "unknown"]))
  }

  func testDesktopMacWithNoLidCanProbeAfterBackoff() {
    let desktopMac = CapturePresence(
      screenLocked: false, displaysAsleep: false, consoleSessionActive: true,
      lidClosed: nil, appActive: true)
    var policy = ArmedCaptureRecoveryPolicy()
    _ = policy.enter(now: start)
    XCTAssertEqual(
      policy.signal(.backoff, now: start.addingTimeInterval(30), presence: desktopMac, inputIsBuiltIn: nil),
      .probe)
  }

  func testOvernightLockEscalatesChecksAndPreservesRetryTelemetryBudget() {
    let locked = CapturePresence(
      screenLocked: true, displaysAsleep: true, consoleSessionActive: true,
      lidClosed: nil, appActive: false)
    let eightHours: TimeInterval = 8 * 60 * 60
    var policy = ArmedCaptureRecoveryPolicy()
    var lifecycleEvents = ArmedLifecycleEventPolicy()
    _ = policy.enter(now: start)
    XCTAssertTrue(lifecycleEvents.shouldEmit(phase: "entered", now: start))
    var skipChecks = 0
    var skipEvents = 0
    var now = start

    while let deadline = policy.nextRetryAt, deadline.timeIntervalSince(start) <= eightHours {
      now = deadline
      guard
        case .retrySkipped(let reason, _) = policy.signal(
          .backoff, now: now, presence: locked, inputIsBuiltIn: nil)
      else {
        XCTFail("locked timer recheck must remain skipped")
        return
      }
      skipChecks += 1
      if lifecycleEvents.shouldEmit(phase: "retry_skipped", presenceReason: reason, now: now) {
        skipEvents += 1
      }
    }
    XCTAssertGreaterThan(skipChecks, 0)
    XCTAssertLessThan(skipChecks, 60, "escalating waits should keep an overnight timer bounded")
    XCTAssertEqual(skipEvents, 1, "an unchanged locked state emits only the first skip event")
    XCTAssertEqual(policy.retryCount, 1, "skipped checks do not consume probe retries")

    let unlockTime = start.addingTimeInterval(eightHours)
    lifecycleEvents.presenceReturned()
    XCTAssertTrue(lifecycleEvents.shouldEmit(phase: "retry", now: unlockTime))
    XCTAssertEqual(
      policy.signal(.unlock, now: unlockTime, presence: present, inputIsBuiltIn: nil), .probe)
  }

  func testRetrySkippedReasonChangesAreDeduplicatedAndSeparatelyCapped() {
    var policy = ArmedLifecycleEventPolicy()
    XCTAssertTrue(policy.shouldEmit(phase: "retry_skipped", presenceReason: .screenLocked, now: start))
    XCTAssertFalse(
      policy.shouldEmit(
        phase: "retry_skipped", presenceReason: .screenLocked, now: start.addingTimeInterval(30)))
    XCTAssertTrue(
      policy.shouldEmit(
        phase: "retry_skipped", presenceReason: .displaysAsleep, now: start.addingTimeInterval(60)))
    XCTAssertTrue(policy.shouldEmit(phase: "retry", now: start.addingTimeInterval(90)))
    XCTAssertTrue(
      policy.shouldEmit(phase: "retry_skipped", presenceReason: .unknown, now: start.addingTimeInterval(120)))
    XCTAssertTrue(
      policy.shouldEmit(
        phase: "retry_skipped", presenceReason: .consoleInactive, now: start.addingTimeInterval(150)))
    XCTAssertFalse(
      policy.shouldEmit(
        phase: "retry_skipped", presenceReason: .lidClosedBuiltIn, now: start.addingTimeInterval(180)),
      "skip events have their own four-per-hour cap")
    XCTAssertFalse(
      policy.shouldEmit(
        phase: "retry_skipped", presenceReason: .lidClosedBuiltIn, now: start.addingTimeInterval(3_600)))
    policy.presenceReturned()
    XCTAssertTrue(
      policy.shouldEmit(
        phase: "retry_skipped", presenceReason: .lidClosedBuiltIn, now: start.addingTimeInterval(3_601)))
  }

  func testManualAndPermissionPoliciesRemainTerminal() {
    XCTAssertEqual(SharedCaptureSilentMicRecoveryPolicy.action(for: 3), .stopAndSurfaceError)
    XCTAssertEqual(
      MicrophoneCaptureAuthorizationPolicy.action(for: .denied, userInitiated: false),
      .abandonAutomaticStart)
    XCTAssertEqual(MicrophoneCaptureAuthorizationPolicy.terminalAlert(for: .denied), .permission)
  }
}
