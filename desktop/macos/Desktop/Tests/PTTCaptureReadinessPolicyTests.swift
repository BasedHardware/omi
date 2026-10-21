import CoreAudio
import VoiceTurnDomain
import XCTest

@testable import Omi_Computer

/// The two pure rules behind the fresh-install first-press gap: when a warm
/// microphone capture may be opened ahead of a press, and how a turn that lost
/// its audio to capture-start latency is judged.
///
/// Sits next to `PushToTalkSpeechGateTests` because it is the same kind of test:
/// the admission/classification decision, not the CoreAudio call it guards.
@MainActor
final class PTTCaptureReadinessPolicyTests: XCTestCase {

  // MARK: - Discard judgement

  /// The observed press: a 947 ms hold whose capture came up at the very end
  /// delivered 0.01 s of audio, was classified `too_short_audible`, and told the
  /// user to hold longer. Capture-start latency is not the user's fault and must
  /// not be charged to the press.
  func testNearlyOneSecondHoldWithLateCaptureIsNotAShortTap() {
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: 0.95, deliveredAudioSeconds: 0.01, minTurnAudioSeconds: 0.35),
      .captureStartedLate)
  }

  /// The same turn, all the way through the recorder: `too_short_audible` is the
  /// class this fix exists to stop producing.
  func testLateCaptureTurnIsNotClassifiedTooShortAudible() {
    let failureClass = PTTAttemptLifecycleRecorder.classify(
      disposition: .silentRejected,
      captureStartOutcome: .accepted,
      hadFirstAudioCallback: true,
      hadFirstUsableFrame: true,
      judgeable: false,
      captureStartedLate: true,
      resolvedRecoveryOutcome: .none)

    XCTAssertNotEqual(failureClass, .tooShortAudible)
    // Same user-visible defect as a start that never resolved, so it lands in the
    // same class and one query sizes the whole first-press gap.
    XCTAssertEqual(failureClass, .captureNeverOperational)
  }

  /// A press that never became operational at all keeps its existing class.
  func testCaptureThatNeverDeliveredACallbackStaysCaptureNeverOperational() {
    XCTAssertEqual(
      PTTAttemptLifecycleRecorder.classify(
        disposition: .tooShort,
        captureStartOutcome: .requested,
        hadFirstAudioCallback: false,
        hadFirstUsableFrame: false,
        judgeable: false,
        resolvedRecoveryOutcome: .none),
      .captureNeverOperational)
  }

  /// A genuine tap keeps the hold-longer hint. The whole point of judging on the
  /// press is that a short press really is short.
  func testGenuineTapIsStillAShortTap() {
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: 0.12, deliveredAudioSeconds: 0.0, minTurnAudioSeconds: 0.35),
      .shortTap)
  }

  /// A healthy hold with nothing said keeps the quiet reset: enough audio
  /// arrived to judge the turn on its content.
  func testHoldThatDeliveredItsAudioIsJudgedOnContent() {
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: 2.0, deliveredAudioSeconds: 2.0, minTurnAudioSeconds: 0.35),
      .audioJudgeable)
  }

  /// Without a press clock there is nothing to charge the latency against, so the
  /// pre-existing delivered-audio rule stands rather than guessing.
  func testMissingPressClockFallsBackToTheDeliveredAudioRule() {
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: nil, deliveredAudioSeconds: 0.01, minTurnAudioSeconds: 0.35),
      .shortTap)
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: nil, deliveredAudioSeconds: 1.0, minTurnAudioSeconds: 0.35),
      .audioJudgeable)
  }

  /// A hold exactly on the gate is not late — it delivered what the gate asks for.
  func testHoldAtTheGateWithFullAudioIsJudgeable() {
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: 0.35, deliveredAudioSeconds: 0.35, minTurnAudioSeconds: 0.35),
      .audioJudgeable)
  }

  // MARK: - The hold clock

  /// The clock must measure the press, not the wait behind it. A cold realtime
  /// hub holds a turn's buffered audio and judges it a second later, on the warm
  /// deadline — which is exactly the fresh-install path, so measuring "now minus
  /// the press" there would turn every accidental tap into a capture failure and
  /// corrupt the metric this fix is judged by.
  func testHoldIsMeasuredToReleaseNotToFinalization() {
    let clock = MutableClock()
    let recorder = PTTAttemptLifecycleRecorder()
    recorder.now = { [clock] in clock.date }
    recorder.beginAttempt(mode: "hold", hubActive: true, micPermissionGranted: true)

    clock.advance(0.2)
    recorder.noteRelease()
    // The hub warm deadline fires a second after the press.
    clock.advance(0.8)

    XCTAssertEqual(recorder.holdSeconds ?? 0, 0.2, accuracy: 0.001)
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: recorder.holdSeconds, deliveredAudioSeconds: 0.15, minTurnAudioSeconds: 0.35),
      .shortTap,
      "a 200 ms tap judged on the hub warm deadline must stay a tap")
  }

  /// The tap-to-lock window is the second post-release wait, it is on by default,
  /// and it is longer than the commit gate. A tap short enough to open it is by
  /// definition shorter than the gate, so it can never be a late capture — but
  /// only while the hold is latched at key-up. Latching at finalization instead
  /// puts every default-install tap at `lockDecision` (0.4 s) ≥ the gate, i.e.
  /// reports every accidental tap as a capture failure.
  func testATapToLockTapCanNeverBeJudgedALateCapture() {
    XCTAssertLessThan(
      PushToTalkManager.tapToLockMaxHoldDuration, PushToTalkManager.minTurnAudioSeconds)
    XCTAssertEqual(
      PTTTurnDiscardJudgement.judge(
        holdSeconds: PushToTalkManager.tapToLockMaxHoldDuration,
        deliveredAudioSeconds: PushToTalkManager.tapToLockMaxHoldDuration,
        minTurnAudioSeconds: PushToTalkManager.minTurnAudioSeconds),
      .shortTap)
  }

  /// The automation bridge drives real push-to-talk turns with the microphone
  /// deliberately bypassed, so nothing ever requests a capture start. Judging
  /// those on their "hold" would make a synthetic turn's disposition — and the
  /// `ptt-lifecycle` e2e flow's expectation — depend on how long the harness took
  /// between two localhost HTTP calls.
  func testATurnThatNeverRequestedACaptureHasNoLatencyToCharge() {
    let recorder = PTTAttemptLifecycleRecorder()
    recorder.beginAttempt(mode: "hold", hubActive: false, micPermissionGranted: false)
    XCTAssertFalse(recorder.captureWasRequested)

    recorder.captureStartRequested()
    XCTAssertTrue(recorder.captureWasRequested)
  }

  /// First call wins: a re-entered finalization must not extend a hold that has
  /// already ended.
  func testReleaseIsLatchedOnce() {
    let clock = MutableClock()
    let recorder = PTTAttemptLifecycleRecorder()
    recorder.now = { [clock] in clock.date }
    recorder.beginAttempt(mode: "hold", hubActive: true, micPermissionGranted: true)

    clock.advance(0.2)
    recorder.noteRelease()
    clock.advance(5.0)
    recorder.noteRelease()

    XCTAssertEqual(recorder.holdSeconds ?? 0, 0.2, accuracy: 0.001)
  }

  // MARK: - Warm capture admission

  func testWarmCaptureIsAdmittedAfterTheCardIsShown() {
    XCTAssertTrue(PTTWarmCaptureAdmission.admits(admissible()))
  }

  /// A prewarm must never be what raises the system microphone prompt: the user
  /// has to see that prompt attached to something they did.
  func testWarmCaptureNeverRequestsMicrophonePermission() {
    var input = admissible()
    input.micPermissionGranted = false

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  func testWarmCaptureIsRefusedWhileATurnOwnsTheDevice() {
    var input = admissible()
    input.hasActiveTurn = true

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  /// Two IOProcs on one input is the hazard the parked-warm mechanism exists to
  /// avoid; a second warm capture beside an existing one would recreate it.
  func testWarmCaptureIsRefusedWhenACaptureAlreadyExists() {
    var input = admissible()
    input.hasCaptureAlready = true

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  func testWarmCaptureIsRefusedWhenPushToTalkIsOff() {
    var input = admissible()
    input.pttEnabled = false

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  func testWarmCaptureIsRefusedBeforeOnboardingCompletesOrWhileSignedOut() {
    var unonboarded = admissible()
    unonboarded.onboardingComplete = false
    XCTAssertFalse(PTTWarmCaptureAdmission.admits(unonboarded))

    var signedOut = admissible()
    signedOut.isSignedIn = false
    XCTAssertFalse(PTTWarmCaptureAdmission.admits(signedOut))
  }

  /// Nothing the user did is behind a warm-up, so it refuses any route it cannot
  /// prove is safe to hold open.
  func testWarmCaptureIsRefusedOnAnUnsafeRoute() {
    var input = admissible()
    input.routeIsSafeToWarmUnattended = false

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  // MARK: - Which device a warm capture may open

  /// Routing has not answered yet. Falling back to the system default here is how
  /// an unattended warm-up opens the AirPods microphone and drops the user's
  /// audio to HFP for the whole keep-alive window.
  func testAnUnresolvedRouteRefusesRatherThanTakingTheSystemDefault() {
    XCTAssertEqual(snapshot(defaultInputResolved: false).unattendedWarmCaptureRoute, .refused)
  }

  /// The microphone picker exists for external and Bluetooth inputs. Opening the
  /// device somebody deliberately chose, unattended, is not a latency
  /// optimization anyone asked for.
  func testAnExplicitMicrophoneChoiceIsNeverWarmedUnattended() {
    XCTAssertEqual(
      snapshot(selectedUID: "ray-ban-meta", selectedDeviceID: 77).unattendedWarmCaptureRoute,
      .refused)
  }

  /// Opening a Bluetooth input flips the headset out of A2DP into HFP.
  func testABluetoothDefaultInputIsNeverWarmedUnattended() {
    XCTAssertEqual(
      snapshot(defaultInputIsBluetooth: true).unattendedWarmCaptureRoute, .refused)
  }

  /// Bluetooth *output* already routes push-to-talk to the built-in microphone;
  /// the warm capture takes the same safe device rather than refusing.
  func testBluetoothOutputWarmsTheBuiltInMicrophone() {
    XCTAssertEqual(
      snapshot(outputIsBluetooth: true, builtInDeviceID: 42, defaultInputIsBluetooth: true)
        .unattendedWarmCaptureRoute,
      .device(42))
  }

  func testAResolvedNonBluetoothDefaultInputIsWarmed() {
    XCTAssertEqual(snapshot().unattendedWarmCaptureRoute, .device(nil))
  }

  private func snapshot(
    selectedUID: String = "",
    selectedDeviceID: AudioDeviceID? = nil,
    outputIsBluetooth: Bool = false,
    builtInDeviceID: AudioDeviceID? = nil,
    defaultInputResolved: Bool = true,
    defaultInputIsBluetooth: Bool = false
  ) -> PTTInputDeviceRouting.Snapshot {
    PTTInputDeviceRouting.Snapshot(
      selectedUID: selectedUID,
      selectedDeviceID: selectedDeviceID,
      outputIsBluetooth: outputIsBluetooth,
      builtInDeviceID: builtInDeviceID,
      defaultInputDeviceID: defaultInputResolved ? 1 : nil,
      defaultInputIsBluetooth: defaultInputIsBluetooth,
      contentionResolved: false)
  }

  /// Injects time so the hold clock is deterministic.
  private final class MutableClock {
    var date = Date()
    func advance(_ seconds: Double) { date.addTimeInterval(seconds) }
  }

  private func admissible() -> PTTWarmCaptureAdmission.Input {
    PTTWarmCaptureAdmission.Input(
      pttEnabled: true,
      micPermissionGranted: true,
      onboardingComplete: true,
      isSignedIn: true,
      routeIsSafeToWarmUnattended: true,
      hasActiveTurn: false,
      hasCaptureAlready: false)
  }
}
