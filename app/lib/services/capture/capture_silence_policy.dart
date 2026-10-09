part of 'capture_coordinator.dart';

/// Timer events are fenced to the recording that armed them, then checked
/// against the current deadline when the serialized reducer runs.
class UplinkSilenceElapsed extends CaptureEvent {
  const UplinkSilenceElapsed(this.recordingId);
  final String? recordingId;
}

class ResumeSilencePaused extends CaptureEvent {
  const ResumeSilencePaused();
}

class SilencePauseMarkerStage extends CaptureStage {
  const SilencePauseMarkerStage(this.paused);
  final bool paused;
}

CaptureTransition _reduceUplinkSilence(
  CaptureCoordinatorState state,
  UplinkSilenceElapsed event,
  CaptureEnvironment env,
) {
  // INV-CAP-1: current live-mode firmware discards queued frames when a
  // connected phone unsubscribes. No shipped retention capability authorizes
  // this automatic pause; even a queued timer event must leave capture live.
  return CaptureTransition(state, const []);
}

CaptureTransition _reduceSilenceResume(CaptureCoordinatorState state, CaptureEnvironment env) {
  if (!env.silencePaused || state.phoneOwns || state.callActive) {
    return CaptureTransition(state, const []);
  }
  final device = state.connectedDevice;
  if (device == null) {
    // Link reconnect remains immediate and will start capture under this intent.
    return CaptureTransition(state, const [PolicyWrite(false)]);
  }
  final seq = state.sessionSeq + 1;
  final key = 'pendant-$seq';
  return CaptureTransition(
    state.copyWith(
      phase: CapturePhase.pendantLive,
      sessionSeq: seq,
      active: () => ActiveCaptureSession(
          source: CaptureSource.pendant,
          mode: CaptureTransport.live,
          sessionKey: key,
          deviceId: device.id,
          deviceType: device.type),
    ),
    [
      const PolicyWrite(false),
      MintRecording(sessionKey: key, telemetrySource: 'pendant_live'),
      const RunStage(StartDeviceSessionStage(deviceRequested: true, promptLocation: false)),
    ],
  );
}

CaptureTransition _reduceDevicePause(CaptureCoordinatorState state, CaptureEnvironment env) {
  if (env.silencePaused) {
    return CaptureTransition(state, const [RunStage(SilencePauseMarkerStage(false))]);
  }
  if (state.phase == CapturePhase.phoneLive || state.phase == CapturePhase.phoneBatchLive) {
    return _reducePause(state, env);
  }
  if (state.phoneOwns) return CaptureTransition(state, const []);
  final nextPhase = switch (state.phase) {
    CapturePhase.pendantLive => CapturePhase.pendantPaused,
    CapturePhase.pendantBatchLive => CapturePhase.pendantBatchPaused,
    _ => state.phase,
  };
  if (nextPhase != state.phase) {
    return CaptureTransition(state.copyWith(phase: nextPhase), const [
      PolicyWrite(true),
      RunStage(PauseDeviceTailStage()),
    ]);
  }
  // An unowned pendant control only records suspended intent; the legacy
  // idle mute persists admission without opening any capture source.
  if (state.pendantSuspension != null) {
    return CaptureTransition(state.copyWith(suspended: _withPendantWasPaused(state.suspended, true)), const []);
  }
  if (state.phase == CapturePhase.idle && !state.callActive) {
    return CaptureTransition(state, const [PolicyWrite(true), RunStage(PauseDeviceTailStage())]);
  }
  return CaptureTransition(state, const []);
}
