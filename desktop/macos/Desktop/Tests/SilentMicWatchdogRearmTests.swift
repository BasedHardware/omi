import CoreFoundation
import XCTest

@testable import Omi_Computer

private final class SilentMicWatchdogRaceBarrier: @unchecked Sendable {
  private let stateLock = NSLock()
  private let releaseEvaluation = DispatchSemaphore(value: 0)
  private var evaluationDidLock = false
  private var resetWillLock = false
  private var evaluationWaiters: [CheckedContinuation<Void, Never>] = []
  private var resetWaiters: [CheckedContinuation<Void, Never>] = []

  func evaluationLocked() {
    let waiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      evaluationDidLock = true
      defer { evaluationWaiters.removeAll() }
      return evaluationWaiters
    }
    for waiter in waiters { waiter.resume() }
  }

  func resetStarted() {
    let waiters = stateLock.withLock { () -> [CheckedContinuation<Void, Never>] in
      resetWillLock = true
      defer { resetWaiters.removeAll() }
      return resetWaiters
    }
    for waiter in waiters { waiter.resume() }
  }

  func waitForEvaluationRelease() {
    releaseEvaluation.wait()
  }

  func releaseEvaluationLock() {
    releaseEvaluation.signal()
  }

  func waitUntilEvaluationLocked() async {
    if stateLock.withLock({ evaluationDidLock }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if evaluationDidLock { return true }
        evaluationWaiters.append(continuation)
        return false
      }
      if shouldResume { continuation.resume() }
    }
  }

  func waitUntilResetStarted() async {
    if stateLock.withLock({ resetWillLock }) { return }
    await withCheckedContinuation { continuation in
      let shouldResume = stateLock.withLock {
        if resetWillLock { return true }
        resetWaiters.append(continuation)
        return false
      }
      if shouldResume { continuation.resume() }
    }
  }
}

/// BL-015 / MIC-05 — the silent-mic watchdog must detect and recover a silent mic more than
/// once within a single capture session, not latch after the first episode. These tests drive
/// `AudioCaptureService.evaluateSilentMicWindow` (the per-window decision extracted from the
/// audio callback) so the fire-more-than-once contract is verified without real CoreAudio buffers.
final class SilentMicWatchdogRearmTests: XCTestCase {

  func testResetClearsStateAfterOverlappingEvaluation() async {
    let svc = makeWatchdog()
    let barrier = SilentMicWatchdogRaceBarrier()
    svc.watchdogSynchronizationHookForTesting = { event in
      switch event {
      case .evaluationDidLock:
        barrier.evaluationLocked()
        barrier.waitForEvaluationRelease()
      case .resetWillLock:
        barrier.resetStarted()
      }
    }

    let evaluationTask = Task.detached {
      _ = svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0)
    }
    await barrier.waitUntilEvaluationLocked()

    let resetTask = Task.detached {
      svc.resetSilentMicWatchdog()
    }
    await barrier.waitUntilResetStarted()
    barrier.releaseEvaluationLock()

    await evaluationTask.value
    await resetTask.value
    svc.watchdogSynchronizationHookForTesting = nil

    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 2))
  }

  func testResetClearsWatchdogEvaluationState() {
    let svc = AudioCaptureService()
    svc.detectSilentMicOnAnyTransport = true

    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    svc.resetSilentMicWatchdog()

    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 2))
  }

  /// PTT opts every transport into detection; without this only Bluetooth inputs fire.
  private func makeWatchdog(anyTransport: Bool = true) -> AudioCaptureService {
    let svc = AudioCaptureService()
    svc.detectSilentMicOnAnyTransport = anyTransport
    svc.resetSilentMicWatchdog()
    return svc
  }

  func testFiresAfterThresholdConsecutiveSilentWindows() {
    let svc = makeWatchdog()
    // One silent window is below the 2-window threshold — no detection yet.
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    // The second consecutive silent window crosses the threshold — fires.
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))
  }

  func testNonSilentWindowResetsRunSoNoFire() {
    let svc = makeWatchdog()
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    // A window with real audio resets the silent run.
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 5000, isBluetooth: false, now: 1))
    // A single silent window after recovery is again below threshold.
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 2))
  }

  /// The core BL-015 regression: a second silent episode later in the SAME session must also
  /// fire, after the recovery cooldown — not be swallowed by a permanent one-shot latch.
  func testSecondEpisodeFiresAgainAfterCooldown() {
    let svc = makeWatchdog()

    // Episode 1 fires at t=1.
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))

    // Within the cooldown the watchdog is suppressed even while the mic is still silent —
    // the freshly rebuilt/switched capture is given time to start delivering real audio.
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 2))
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 3))

    // Mic recovers, then re-wedges after the cooldown has elapsed.
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 8000, isBluetooth: false, now: 5))
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 6))
    // Episode 2 fires — proving detection more than once per session.
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 7))
  }

  /// Tight-loop guard: an unrecoverable mic cannot fire endlessly — capped per session even
  /// when every window is spaced past the cooldown so re-arm is never the limiter.
  func testFireCountIsCappedPerSession() {
    let svc = makeWatchdog()
    var fires = 0
    var t: CFAbsoluteTime = 0
    for _ in 0..<40 {
      if svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: t) != nil { fires += 1 }
      t += 4  // > cooldown, so the per-session cap is what stops it
    }
    XCTAssertEqual(fires, 3, "watchdog must cap silent-mic recovery attempts per session")
  }

  /// A new capture session (start/stop calls `resetSilentMicWatchdog`) starts fresh even after
  /// the previous session exhausted the per-session cap.
  func testResetReArmsForANewSession() {
    let svc = makeWatchdog()
    var t: CFAbsoluteTime = 0
    for _ in 0..<40 {
      _ = svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: t)
      t += 4
    }

    svc.resetSilentMicWatchdog()
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: t))
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: t + 1))
  }

  /// Non-Bluetooth silence only fires when the owner (PTT) opted into all-transport detection.
  func testNonBluetoothSilenceRequiresAnyTransportOptIn() {
    let svc = makeWatchdog(anyTransport: false)
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 0))
    XCTAssertNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: false, now: 1))
    // Same silence classified as Bluetooth still fires without the opt-in.
    XCTAssertNotNil(svc.evaluateSilentMicWindow(peak: 0, isBluetooth: true, now: 2))
  }
}
