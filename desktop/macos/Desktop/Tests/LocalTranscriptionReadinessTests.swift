import XCTest

@testable import Omi_Computer

/// Warming the on-device speaker models runs alongside the Parakeet load but must never gate
/// transcription readiness. QA measured ~20s of silent transcript at every capture-session
/// start when readiness awaited the diarizer behind a "grace" deadline: `withTaskGroup`
/// implicitly awaits an unfinished `Task.value` child and `Task.value` ignores cancellation,
/// so the deadline could not fire — readiness blocked for exactly as long as the speaker
/// models took, on every capture session.
final class LocalTranscriptionReadinessTests: XCTestCase {
  /// Minimal deterministic event: `wait` resolves once (or after) `signal` happened.
  private final class OneShotEvent: @unchecked Sendable {
    private let lock = NSLock()
    private var isSignaled = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func signal() {
      lock.lock()
      isSignaled = true
      let waiters = self.waiters
      self.waiters = []
      lock.unlock()
      waiters.forEach { $0.resume() }
    }

    func wait() async {
      await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        lock.lock()
        if isSignaled {
          lock.unlock()
          continuation.resume()
          return
        }
        waiters.append(continuation)
        lock.unlock()
      }
    }
  }

  private actor WarmupState {
    private(set) var finished = false
    func markFinished() { finished = true }
  }

  func testReadinessIsGrantedWhileSpeakerWarmupIsStillInFlight() async throws {
    let warmupBlocked = OneShotEvent()
    let releaseWarmup = OneShotEvent()
    let state = WarmupState()

    let warmup: @Sendable () async -> Void = {
      warmupBlocked.signal()
      await releaseWarmup.wait()
      await state.markFinished()
    }

    struct LoadedASR: Sendable {}
    let manager = try await LocalTranscriptionService.loadASRManagerWithSpeakerWarmup(
      loadASR: { LoadedASR() },
      warmSpeakerModels: warmup)

    // The load returned on its own; only then does the test let the warmup pass its gate.
    // If readiness awaited the warmup, the warmup would still be blocked on
    // `releaseWarmup`, this function could never have returned, and the test would hang.
    await warmupBlocked.wait()
    let finished = await state.finished
    XCTAssertFalse(finished, "speaker warmup must still be in flight when readiness is granted")
    XCTAssertNotNil(manager)

    releaseWarmup.signal()
    // Nothing dangles: the warmup runs to completion now that it is released.
    while !(await state.finished) {
      await Task.yield()
    }
  }
}
