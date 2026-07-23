import XCTest

@testable import Omi_Computer

#if DEBUG
  /// Behavioral tests for `PTTAttemptLifecycleRecorder` — the privacy-bounded
  /// capture-lifecycle correlation model. These drive the production API with an
  /// injected clock so every failure classification, timing bucket, and recovery
  /// correlation is verified deterministically without real CoreAudio.
  @MainActor
  final class PTTAttemptLifecycleRecorderTests: XCTestCase {

    // MARK: - Failure classification 1: capture never became operational

    func testCaptureStartFailedClassifiesNeverOperational() {
      let recorder = makeRecorder()
      begin(recorder)
      recorder.captureStartRequested()
      recorder.captureStartResolved(
        outcome: .failed,
        statusClass: .from(
          error: AudioCaptureService.AudioCaptureError.engineStartFailed(NSError(domain: "x", code: 1))))

      let snap = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      XCTAssertEqual(snap.failureClass, .captureNeverOperational)
      XCTAssertEqual(snap.captureStartOutcome, .failed)
      XCTAssertEqual(snap.captureStartStatusClass, .engineStartFailed)
    }

    func testStartupRaceNoAudioCallbackClassifiesNeverOperational() {
      // Capture was accepted but never delivered a callback before the turn ended.
      let recorder = makeRecorder()
      begin(recorder)
      recorder.captureStartRequested()
      recorder.captureStartResolved(outcome: .accepted, statusClass: .ok)

      let snap = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      XCTAssertEqual(snap.failureClass, .captureNeverOperational)
      XCTAssertEqual(snap.captureStartOutcome, .accepted)
      XCTAssertEqual(snap.msToFirstAudioBucket, .none)
      XCTAssertEqual(snap.firstChunksEnergyBucket, .none)
    }

    // MARK: - Failure classification 2: zero / near-zero samples

    func testOperationalCaptureWithOnlyZeroSamplesClassifiesZeroSamples() {
      let recorder = makeRecorder()
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.silentPCM(sampleCount: 320))
      recorder.ingestAudioChunk(Self.silentPCM(sampleCount: 320))

      let snap = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      XCTAssertEqual(snap.failureClass, .zeroOrNearZeroSamples)
      XCTAssertNotEqual(snap.msToFirstAudioBucket, .none, "first audio callback was recorded")
      XCTAssertEqual(snap.msToFirstUsableFrameBucket, .none, "no usable frame ever arrived")
      XCTAssertEqual(snap.firstChunksEnergyBucket, .zero)
    }

    // MARK: - Failure classification 3: released before first usable audio

    func testReleasedBeforeUsableAudioForTooShortTurn() {
      let recorder = makeRecorder()
      begin(recorder)
      captureAccepted(recorder)
      // Callbacks arrived but were zero; the key came up before usable audio.
      recorder.ingestAudioChunk(Self.silentPCM(sampleCount: 160))

      let snap = terminate(recorder, disposition: .tooShort, peak: 0, rms: 0, seconds: 0.1, judgeable: false)

      XCTAssertEqual(snap.failureClass, .releasedBeforeUsableAudio)
      XCTAssertNotEqual(snap.msToFirstAudioBucket, .none)
      XCTAssertEqual(snap.msToFirstUsableFrameBucket, .none)
    }

    // MARK: - Success: committed

    func testCommittedTurnWithUsableAudioClassifiesCommitted() {
      let recorder = makeRecorder()
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.audiblePCM(sampleCount: 320))

      let snap = terminate(recorder, disposition: .committed, peak: 4000, rms: 800, seconds: 1.5, judgeable: true)

      XCTAssertEqual(snap.failureClass, .committed)
      XCTAssertEqual(snap.firstChunksEnergyBucket, .audible)
      XCTAssertNotEqual(snap.msToFirstUsableFrameBucket, .none)
    }

    // MARK: - Failure classification 4: recovery attempt outcome

    func testRecoveryTriggeredEmitsCorrelationIdAndResolvedRecoveredOnNextTurn() {
      let recorder = makeRecorder()
      // Attempt 1: silent capture triggers a rebuild.
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.silentPCM(sampleCount: 320))
      recorder.recoveryTriggered(action: .captureRebuild)
      let first = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      XCTAssertTrue(first.recoveryTriggered)
      XCTAssertEqual(first.recoveryAction, .captureRebuild)
      let recoveryId = first.recoveryAttemptId
      XCTAssertNotNil(recoveryId)

      // Attempt 2: capture restored — usable audio resolves the recovery.
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.audiblePCM(sampleCount: 320))
      let second = terminate(recorder, disposition: .committed, peak: 4000, rms: 800, seconds: 1.5, judgeable: true)

      XCTAssertFalse(second.recoveryTriggered)
      XCTAssertEqual(second.recoveryAttemptId, recoveryId)
      XCTAssertEqual(second.recoveryOutcomeOfNextTurn, .recovered)
      XCTAssertEqual(second.failureClass, .recoveryOutcomeRecovered)
    }

    func testRecoveryResolvedStillSilentOnNextSilentTurn() {
      let recorder = makeRecorder()
      begin(recorder)
      captureAccepted(recorder)
      recorder.recoveryTriggered(action: .captureRebuild)
      _ = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.silentPCM(sampleCount: 320))
      let second = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      XCTAssertEqual(second.recoveryOutcomeOfNextTurn, .stillSilent)
      XCTAssertEqual(second.failureClass, .recoveryOutcomeStillSilent)
    }

    func testNonJudgeableTurnDoesNotConsumePendingRecovery() {
      let recorder = makeRecorder()
      begin(recorder)
      captureAccepted(recorder)
      recorder.recoveryTriggered(action: .captureRebuild)
      _ = terminate(recorder, disposition: .silentRejected, peak: 0, rms: 0, seconds: 1.0, judgeable: true)

      // A too-short, non-judgeable turn must NOT resolve the recovery.
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.audiblePCM(sampleCount: 80))
      let nonJudgeable = terminate(
        recorder, disposition: .tooShort, peak: 3000, rms: 600, seconds: 0.1, judgeable: false)

      XCTAssertEqual(nonJudgeable.recoveryOutcomeOfNextTurn, .notJudgeable)
      XCTAssertNotNil(nonJudgeable.recoveryAttemptId)

      // The next truly judgeable turn resolves it.
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.audiblePCM(sampleCount: 320))
      let resolving = terminate(recorder, disposition: .committed, peak: 4000, rms: 800, seconds: 1.5, judgeable: true)

      XCTAssertEqual(resolving.recoveryOutcomeOfNextTurn, .recovered)
    }

    // MARK: - Timing buckets

    func testFirstAudioAndUsableFrameBucketsReflectElapsedMs() {
      let clock = MutableTestClock()
      let recorder = makeRecorder(clock: clock)
      begin(recorder)
      captureAccepted(recorder)
      // Advance ~120ms before the first callback, then ~80ms to a usable frame.
      clock.advance(milliseconds: 120)
      recorder.ingestAudioChunk(Self.silentPCM(sampleCount: 160))
      clock.advance(milliseconds: 80)
      recorder.ingestAudioChunk(Self.audiblePCM(sampleCount: 320))

      let snap = terminate(recorder, disposition: .committed, peak: 4000, rms: 800, seconds: 1.0, judgeable: true)

      XCTAssertEqual(snap.msToFirstAudioBucket, .lt200)  // 120ms → lt_200
      XCTAssertEqual(snap.msToFirstUsableFrameBucket, .lt500)  // 200ms → lt_500
    }

    // MARK: - Static classification precedence

    func testClassificationPrecedencePlacesCaptureStartFailureAboveZeroSamples() {
      let cls = PTTAttemptLifecycleRecorder.classify(
        disposition: .silentRejected,
        captureStartOutcome: .failed,
        hadFirstAudioCallback: true,
        hadFirstUsableFrame: false,
        isNearZero: true,
        judgeable: true,
        resolvedRecoveryOutcome: .none)
      XCTAssertEqual(cls, .captureNeverOperational)
    }

    func testClassificationPrecedenceRecoveryOutcomeDominates() {
      let cls = PTTAttemptLifecycleRecorder.classify(
        disposition: .silentRejected,
        captureStartOutcome: .accepted,
        hadFirstAudioCallback: true,
        hadFirstUsableFrame: true,
        isNearZero: true,
        judgeable: true,
        resolvedRecoveryOutcome: .recovered)
      XCTAssertEqual(cls, .recoveryOutcomeRecovered)
    }

    // MARK: - Privacy: only bounded fields, never raw device identity or audio

    func testEmittedSnapshotCarriesOnlyBoundedLowCardinalityFields() {
      let recorder = makeRecorder()
      begin(recorder)
      captureAccepted(recorder)
      recorder.ingestAudioChunk(Self.audiblePCM(sampleCount: 320))
      recorder.noteInputRoute(class: .bluetooth, source: .override)
      recorder.noteRouteChanged()
      let snap = terminate(recorder, disposition: .committed, peak: 4000, rms: 800, seconds: 1.5, judgeable: true)

      let props = snap.properties
      // Every value is a String, Bool, Int, or Double — never Data/raw audio.
      for (key, value) in props {
        switch value {
        case is String, is Bool, is Int, is Double:
          break
        default:
          XCTFail("Field \(key) emitted a non-bounded value type: \(type(of: value))")
        }
      }
      // No raw device names / hardware IDs / paths / errors leak.
      let forbidden = ["device_description", "device_name", "hardware_id", "file_path", "error_description"]
      for key in forbidden {
        XCTAssertNil(props[key], "forbidden raw field \(key) present")
      }
      XCTAssertEqual(props["input_route_class"] as? String, "bluetooth")
      XCTAssertEqual(props["input_route_source"] as? String, "override")
      XCTAssertEqual(props["route_changed_during_attempt"] as? Bool, true)
    }

    func testPeakAmplitudeOfZeroBufferIsZero() {
      XCTAssertEqual(PTTAttemptLifecycleRecorder.peakAmplitude(pcm16k: Self.silentPCM(sampleCount: 320)), 0)
    }

    func testPeakAmplitudeOfAudibleBufferExceedsThreshold() {
      XCTAssertGreaterThan(PTTAttemptLifecycleRecorder.peakAmplitude(pcm16k: Self.audiblePCM(sampleCount: 320)), 50)
    }

    // MARK: - Helpers

    private func makeRecorder(clock: MutableTestClock = MutableTestClock()) -> PTTAttemptLifecycleRecorder {
      let recorder = PTTAttemptLifecycleRecorder()
      recorder.now = { [clock] in clock.date }
      return recorder
    }

    private func begin(_ recorder: PTTAttemptLifecycleRecorder) {
      recorder.beginAttempt(mode: "hold", hubActive: true, micPermissionGranted: true)
    }

    private func captureAccepted(_ recorder: PTTAttemptLifecycleRecorder) {
      recorder.captureStartRequested()
      recorder.captureStartResolved(outcome: .accepted, statusClass: .ok)
    }

    private func terminate(
      _ recorder: PTTAttemptLifecycleRecorder,
      disposition: PTTAttemptLifecycleRecorder.TurnDisposition,
      peak: Int,
      rms: Int,
      seconds: Double,
      judgeable: Bool
    ) -> PTTAttemptLifecycleRecorder.Snapshot {
      recorder.terminate(
        disposition: disposition,
        source: "hub",
        peak: peak,
        rms: rms,
        turnAudioSeconds: seconds,
        voicedAudioSeconds: nil,
        isNearZero: peak <= 5 && rms <= 5,
        judgeable: judgeable)
    }

    private static func silentPCM(sampleCount: Int) -> Data {
      Data(count: sampleCount * MemoryLayout<Int16>.size)
    }

    private static func audiblePCM(sampleCount: Int) -> Data {
      var data = Data(count: sampleCount * MemoryLayout<Int16>.size)
      data.withUnsafeMutableBytes { raw in
        let samples = raw.bindMemory(to: Int16.self)
        for i in 0..<sampleCount {
          samples[i] = Int16(1000)
        }
      }
      return data
    }
  }

  /// Injects time in fixed millisecond steps so timing buckets are deterministic.
  private final class MutableTestClock {
    fileprivate var date = Date()
    func advance(milliseconds ms: Int) {
      date.addTimeInterval(TimeInterval(ms) / 1000.0)
    }
  }
#endif
