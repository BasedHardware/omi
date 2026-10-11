import CoreAudio
import Foundation

@MainActor
extension AppState {
  func recordSilentMicDiagnostic(
    detection: AudioCaptureService.SilentMicDetection?,
    phase: String, result: String
  ) {
    let attemptID = captureAttempt?.attemptId ?? armedMicrophoneRecovery.episodeID
    guard silentMicDiagnosticLimit.allow(attemptID: attemptID, now: Date()) else { return }
    let deviceID = detection?.deviceID ?? audioCaptureService?.activeDeviceID
    let defaultID = AudioCaptureService.currentDefaultInputDeviceID()
    let facts = SilentMicHALSnapshot.collect(deviceID: deviceID)
    let peak = detection?.peak ?? 0
    let snapshot = SilentMicDiagnosticTelemetry.Snapshot(
      attemptID: attemptID, recoveryAttempt: silentMicRecoveryAttempts,
      phase: phase, result: result,
      launchContext: captureAttempt?.launchContext ?? CaptureLaunchContext.kind.rawValue,
      updateAttemptID: captureAttempt?.updateAttemptID ?? CaptureLaunchContext.updateAttemptID,
      secondsSinceLaunch: CaptureLaunchContext.timeBucket(
        Date().timeIntervalSince(CaptureLaunchContext.launchedAt)),
      secondsSinceWake: CaptureLaunchContext.timeBucket(
        lastCaptureWakeAt.map { Date().timeIntervalSince($0) }),
      secondsSinceUnlock: CaptureLaunchContext.timeBucket(
        lastCaptureUnlockAt.map { Date().timeIntervalSince($0) }),
      presence: CapturePresence.current(), transport: facts.transport,
      isSystemDefault: deviceID.flatMap { id in defaultID.map { id == $0 } },
      healedRouteOverride: silentMicHealedDeviceID != nil,
      deviceIsAlive: facts.alive, deviceIsRunningSomewhere: facts.running,
      hogModePIDPresent: facts.hog,
      nominalSampleRate: SilentMicDiagnosticTelemetry.rateBucket(facts.rate),
      channelCount: facts.channels.map(SilentMicDiagnosticTelemetry.countBucket) ?? "unknown",
      inputDeviceCount: SilentMicDiagnosticTelemetry.countBucket(facts.inputCount),
      defaultInputChangedSinceLaunch: defaultID.flatMap { current in
        CaptureLaunchContext.defaultInputAtLaunch.map { current != $0 }
      },
      framesReceived: SilentMicDiagnosticTelemetry.countBucket(detection?.framesReceived ?? 0),
      signalClass: detection == nil ? "unknown" : peak == 0 ? "all_zero" : "below_threshold",
      peak: peak == 0 ? "zero" : "one_to_five",
      timeToFirstFrame: CaptureLaunchContext.timeBucket(detection?.secondsToFirstFrame),
      micAuthorization: SilentMicDiagnosticTelemetry.authorization(
        AudioCaptureService.authorizationStatus()))
    PostHogManager.shared.track(
      SilentMicDiagnosticTelemetry.eventName,
      properties: SilentMicDiagnosticTelemetry.properties(snapshot))
  }
}
