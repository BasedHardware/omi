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

  // MARK: - Warm capture admission

  func testWarmCaptureIsAdmittedAfterTheCardIsShown() {
    XCTAssertTrue(PTTWarmCaptureAdmission.admits(admissible(trigger: .firstRealAppCard)))
  }

  /// A prewarm must never be what raises the system microphone prompt: the user
  /// has to see that prompt attached to something they did.
  func testWarmCaptureNeverRequestsMicrophonePermission() {
    var input = admissible(trigger: .firstRealAppCard)
    input.micPermissionGranted = false

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  func testWarmCaptureIsRefusedWhileATurnOwnsTheDevice() {
    var input = admissible(trigger: .onboardingCompleted)
    input.hasActiveTurn = true

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  /// Two IOProcs on one input is the hazard the parked-warm mechanism exists to
  /// avoid; a second warm capture beside an existing one would recreate it.
  func testWarmCaptureIsRefusedWhenACaptureAlreadyExists() {
    var input = admissible(trigger: .ambientCaptureStarted)
    input.hasCaptureAlready = true

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  func testWarmCaptureIsRefusedWhenPushToTalkIsOff() {
    var input = admissible(trigger: .launch)
    input.pttEnabled = false

    XCTAssertFalse(PTTWarmCaptureAdmission.admits(input))
  }

  func testWarmCaptureIsRefusedBeforeOnboardingCompletesOrWhileSignedOut() {
    var unonboarded = admissible(trigger: .firstRealAppCard)
    unonboarded.onboardingComplete = false
    XCTAssertFalse(PTTWarmCaptureAdmission.admits(unonboarded))

    var signedOut = admissible(trigger: .firstRealAppCard)
    signedOut.isSignedIn = false
    XCTAssertFalse(PTTWarmCaptureAdmission.admits(signedOut))
  }

  /// Launch is the only trigger with no user action behind it. Outside the
  /// first-run window it must not light the microphone indicator on every launch
  /// for the life of the install.
  func testLaunchWarmupIsConfinedToTheFirstRunWindow() {
    XCTAssertTrue(PTTWarmCaptureAdmission.admits(admissible(trigger: .launch)))

    var settledInstall = admissible(trigger: .launch)
    settledInstall.isFirstRunWindow = false
    XCTAssertFalse(PTTWarmCaptureAdmission.admits(settledInstall))
  }

  /// Every other trigger follows something the user just did, so it is not
  /// confined that way.
  func testUserFollowingTriggersAreNotConfinedToTheFirstRunWindow() {
    for trigger in [
      PTTWarmCaptureAdmission.Trigger.onboardingCompleted, .firstRealAppCard,
      .ambientCaptureStarted, .captureNotReady,
    ] {
      var input = admissible(trigger: trigger)
      input.isFirstRunWindow = false
      XCTAssertTrue(
        PTTWarmCaptureAdmission.admits(input),
        "\(trigger.rawValue) must warm outside the first-run window")
    }
  }

  private func admissible(
    trigger: PTTWarmCaptureAdmission.Trigger
  ) -> PTTWarmCaptureAdmission.Input {
    PTTWarmCaptureAdmission.Input(
      trigger: trigger,
      pttEnabled: true,
      micPermissionGranted: true,
      onboardingComplete: true,
      isSignedIn: true,
      hasActiveTurn: false,
      hasCaptureAlready: false,
      isFirstRunWindow: true)
  }
}
