import 'dart:async';
import 'dart:convert';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/batch_recording.dart';
import 'package:omi/utils/enums.dart';

/// Capture ownership coordinator: the single admission and ordering authority
/// for "one live source at a time" (CAPTURE_POLICY.md). Every
/// ownership-relevant entry becomes a [CaptureEvent] through [dispatch]; the
/// pure reducer [transitionCapture] maps (state, event, environment) to the
/// next [CaptureCoordinatorState] plus ordered [CaptureEffect]s, and the
/// dispatcher executes them through [CaptureEffectPorts] before publishing the
/// committed state and its durable snapshot. Fail-closed on effect failure.
/// See CAPTURE_ARCHITECTURE.md for invariants and the staged migration table.

// ---------------------------------------------------------------------------
// Logical capture model
// ---------------------------------------------------------------------------

/// Which source can own the capture channel.
enum CaptureSource { pendant, phone }

/// How a source captures: realtime socket streaming or Transcribe Later
/// (native .bin writer, no socket).
enum CaptureTransport { live, batch }

/// Who suspended a capture.
enum SuspendReason { phone, call }

/// The single explicit capture phase. The reducer is the only writer.
enum CapturePhase {
  /// No source owns capture.
  idle,

  /// Connected pendant streaming (or muted-but-connected) in realtime mode.
  pendantLive,
  pendantPaused,

  /// Connected pendant in Transcribe Later mode; the native writer owns the
  /// audio under the shared policy.
  pendantBatchLive,
  pendantBatchPaused,

  /// Phone mic live: AudioSource + WAL + socket.
  phoneLive,

  /// Phone mic paused: microphone released, socket and recording id kept.
  phonePaused,

  /// Phone mic Transcribe Later: native recorder writes .bin directly.
  phoneBatchLive,

  /// Phone batch muted: the native writer drops packets, same file.
  phoneBatchPaused,

  /// An Omi call holds the channel; the previous owner is suspended.
  callActive,

  /// OS audio interruption over a live phone session (call, Siri, alarm).
  /// The phone session stays the owner; native recovers it.
  audioInterrupted,
}

/// The capture session a phase currently runs. Immutable; a fresh
/// [sessionKey] is minted for every new ownership session while [recordingId]
/// carries the client conversation id once the start effect mints it.
class ActiveCaptureSession {
  const ActiveCaptureSession({
    required this.source,
    required this.mode,
    required this.sessionKey,
    this.recordingId,
    this.deviceId,
    this.deviceType,
  });

  final CaptureSource source;
  final CaptureTransport mode;

  /// Coordinator-minted logical session identity, e.g. `phone-3`. Fresh on
  /// every new session; preserved across a call suspension.
  final String sessionKey;

  /// The client conversation id for /v4/listen and analytics. A phone pause /
  /// resume keeps it; a call suspension restores it; a phone-handoff resume
  /// mints a new one.
  final String? recordingId;

  final String? deviceId;
  final DeviceType? deviceType;

  ActiveCaptureSession copyWith({
    String? recordingId,
    String? deviceId,
    DeviceType? deviceType,
  }) =>
      ActiveCaptureSession(
        source: source,
        mode: mode,
        sessionKey: sessionKey,
        recordingId: recordingId ?? this.recordingId,
        deviceId: deviceId ?? this.deviceId,
        deviceType: deviceType ?? this.deviceType,
      );

  Map<String, Object?> toJson() => {
        'source': source.name,
        'mode': mode.name,
        'sessionKey': sessionKey,
        'recordingId': recordingId,
        'deviceId': deviceId,
        'deviceType': deviceType?.name,
      };

  factory ActiveCaptureSession.fromJson(Map<String, dynamic> json) {
    return ActiveCaptureSession(
      source: _parseSource(json['source']),
      mode: _parseTransport(json['mode']),
      sessionKey: _parseString(json['sessionKey'], 'sessionKey'),
      recordingId: json['recordingId'] as String?,
      deviceId: json['deviceId'] as String?,
      deviceType: _parseDeviceType(json['deviceType']),
    );
  }
}

/// A capture pushed onto the LIFO suspension stack while another source owns
/// the channel. Everything needed to put it back is recorded here.
class SuspendedCapture {
  const SuspendedCapture({
    required this.source,
    required this.reason,
    required this.wasPaused,
    required this.mode,
    this.sessionKey,
    this.recordingId,
    this.deviceId,
    this.deviceType,
  });

  final CaptureSource source;

  /// Which owner suspended this capture; only that owner releases it.
  final SuspendReason reason;

  /// The user had it paused before the suspension; it comes back paused.
  final bool wasPaused;

  final CaptureTransport mode;

  /// Kept so a call-resume restores the exact session (conversation id).
  final String? sessionKey;
  final String? recordingId;

  final String? deviceId;
  final DeviceType? deviceType;

  SuspendedCapture withReason(SuspendReason next) => SuspendedCapture(
        source: source,
        reason: next,
        wasPaused: wasPaused,
        mode: mode,
        sessionKey: sessionKey,
        recordingId: recordingId,
        deviceId: deviceId,
        deviceType: deviceType,
      );

  Map<String, Object?> toJson() => {
        'source': source.name,
        'reason': reason.name,
        'wasPaused': wasPaused,
        'mode': mode.name,
        'sessionKey': sessionKey,
        'recordingId': recordingId,
        'deviceId': deviceId,
        'deviceType': deviceType?.name,
      };

  factory SuspendedCapture.fromJson(Map<String, dynamic> json) {
    return SuspendedCapture(
      source: _parseSource(json['source']),
      reason: _parseSuspendReason(json['reason']),
      wasPaused: _parseBool(json['wasPaused'], 'wasPaused'),
      mode: _parseTransport(json['mode']),
      sessionKey: json['sessionKey'] as String?,
      recordingId: json['recordingId'] as String?,
      deviceId: json['deviceId'] as String?,
      deviceType: _parseDeviceType(json['deviceType']),
    );
  }
}

/// Pendant identity as the coordinator tracks it. The controller keeps the
/// rich [BtDevice]; ownership decisions only need id + type.
class ConnectedDevice {
  const ConnectedDevice({required this.id, required this.type});

  final String id;
  final DeviceType type;

  Map<String, Object?> toJson() => {'id': id, 'type': type.name};

  factory ConnectedDevice.fromJson(Map<String, dynamic> json) => ConnectedDevice(
        id: _parseString(json['id'], 'id'),
        type: _parseDeviceTypeRequired(json['type']),
      );
}

/// Immutable coordinator state. Every field needed to reason about ownership
/// is explicit; nothing about hardware health is claimed beyond the last
/// committed transition.
class CaptureCoordinatorState {
  CaptureCoordinatorState({
    required this.phase,
    this.active,
    List<SuspendedCapture> suspended = const [],
    this.connectedDevice,
    this.callActive = false,
    this.micInterrupted = false,
    this.mutedBeforePhone,
    this.sessionSeq = 0,
    this.lastFailure,
  }) : suspended = List.unmodifiable(suspended);

  factory CaptureCoordinatorState.idle({int sessionSeq = 0}) =>
      CaptureCoordinatorState(phase: CapturePhase.idle, sessionSeq: sessionSeq);

  final CapturePhase phase;

  /// The session the current phase runs; null in idle and callActive.
  final ActiveCaptureSession? active;

  /// LIFO suspension stack; the most recently suspended capture is last.
  final List<SuspendedCapture> suspended;

  /// The pendant identity last reported by the device provider.
  final ConnectedDevice? connectedDevice;

  /// An Omi call is connecting/ringing/active (event mirror).
  final bool callActive;

  /// The native phone-mic interruption mirror. Only meaningful for phone
  /// phases; kept separate from [phase] so a paused session stays paused.
  final bool micInterrupted;

  /// The policy the current phone recording started from; restored on a user
  /// stop so stopping the phone never leaves the next source paused.
  final bool? mutedBeforePhone;

  /// Monotonic counter feeding fresh session keys.
  final int sessionSeq;

  /// Last effect failure, for diagnostics and snapshot forensics.
  final String? lastFailure;

  bool get phoneOwns => switch (phase) {
        CapturePhase.phoneLive ||
        CapturePhase.phonePaused ||
        CapturePhase.phoneBatchLive ||
        CapturePhase.phoneBatchPaused ||
        CapturePhase.audioInterrupted =>
          true,
        _ => false,
      };

  bool get pendantOwns => switch (phase) {
        CapturePhase.pendantLive ||
        CapturePhase.pendantPaused ||
        CapturePhase.pendantBatchLive ||
        CapturePhase.pendantBatchPaused =>
          true,
        _ => false,
      };

  SuspendedCapture? get pendantSuspension {
    for (var i = suspended.length - 1; i >= 0; i--) {
      final entry = suspended[i];
      if (entry.source == CaptureSource.pendant) return entry;
    }
    return null;
  }

  /// A connected, non-suspended, realtime pendant that another source would
  /// have to take over from. Batch pendants write natively and are never
  /// handed off.
  bool get pendantHoldsCapture =>
      connectedDevice != null && (phase == CapturePhase.pendantLive || phase == CapturePhase.pendantPaused);

  String nextSessionKey(CaptureSource source) => '${source.name}-${sessionSeq + 1}';

  CaptureCoordinatorState copyWith({
    CapturePhase? phase,
    ActiveCaptureSession? Function()? active,
    List<SuspendedCapture>? suspended,
    ConnectedDevice? Function()? connectedDevice,
    bool? callActive,
    bool? micInterrupted,
    bool? Function()? mutedBeforePhone,
    int? sessionSeq,
    String? Function()? lastFailure,
  }) =>
      CaptureCoordinatorState(
        phase: phase ?? this.phase,
        active: active != null ? active() : this.active,
        suspended: suspended ?? this.suspended,
        connectedDevice: connectedDevice != null ? connectedDevice() : this.connectedDevice,
        callActive: callActive ?? this.callActive,
        micInterrupted: micInterrupted ?? this.micInterrupted,
        mutedBeforePhone: mutedBeforePhone != null ? mutedBeforePhone() : this.mutedBeforePhone,
        sessionSeq: sessionSeq ?? this.sessionSeq,
        lastFailure: lastFailure != null ? lastFailure() : this.lastFailure,
      );

  /// Fail-closed form committed when an effect fails mid-transition: ownership
  /// and suspension debt are cleared so recovery events can start safely —
  /// only the monotonic [sessionSeq] and the known connected identity survive.
  CaptureCoordinatorState failedClosed(Object error) => copyWith(
        phase: CapturePhase.idle,
        active: () => null,
        suspended: const [],
        callActive: false,
        micInterrupted: false,
        mutedBeforePhone: () => null,
        lastFailure: () => error.toString(),
      );

  /// Launch restore is always idle: ownership and suspension debt are dropped
  /// (see CAPTURE_ARCHITECTURE.md); only the session counter survives.
  CaptureCoordinatorState sanitizedForLaunch() => CaptureCoordinatorState.idle(sessionSeq: sessionSeq);

  static const int snapshotVersion = 1;

  Map<String, Object?> toJson() => {
        'version': snapshotVersion,
        'phase': phase.name,
        'active': active?.toJson(),
        'suspended': suspended.map((e) => e.toJson()).toList(),
        'connectedDevice': connectedDevice?.toJson(),
        'callActive': callActive,
        'micInterrupted': micInterrupted,
        'mutedBeforePhone': mutedBeforePhone,
        'sessionSeq': sessionSeq,
        'lastFailure': lastFailure,
      };

  String encode() => jsonEncode(toJson());

  /// Strict parse: every field [toJson] writes is required and type-checked,
  /// and phase/session consistency is validated. Any malformed input throws;
  /// [tryParse] maps that to a conservative idle restore.
  factory CaptureCoordinatorState.fromJson(Map<String, dynamic> json) {
    final version = json['version'];
    if (version is! int || version != snapshotVersion) {
      throw const FormatException('Unsupported capture snapshot version');
    }
    final phase = _parsePhase(json['phase']);
    final activeRaw = json['active'];
    final active = switch (activeRaw) {
      null => null,
      Map<String, dynamic>() => ActiveCaptureSession.fromJson(activeRaw),
      _ => throw const FormatException('Malformed active session'),
    };
    final suspendedRaw = json['suspended'];
    if (suspendedRaw is! List) throw const FormatException('Missing suspended');
    final suspended = [
      for (final entry in suspendedRaw)
        if (entry is Map<String, dynamic>)
          SuspendedCapture.fromJson(entry)
        else
          throw const FormatException('Malformed suspended capture'),
    ];
    final connectedDeviceRaw = json['connectedDevice'];
    final connectedDevice = switch (connectedDeviceRaw) {
      null => null,
      Map<String, dynamic>() => ConnectedDevice.fromJson(connectedDeviceRaw),
      _ => throw const FormatException('Malformed connected device'),
    };
    final callActive = _parseBool(json['callActive'], 'callActive');
    final micInterrupted = _parseBool(json['micInterrupted'], 'micInterrupted');
    final mutedBeforePhone = json['mutedBeforePhone'];
    if (mutedBeforePhone is! bool?) throw const FormatException('Malformed mutedBeforePhone');
    final sessionSeq = json['sessionSeq'];
    if (sessionSeq is! int) throw const FormatException('Missing sessionSeq');
    final lastFailure = json['lastFailure'];
    if (lastFailure is! String?) throw const FormatException('Malformed lastFailure');

    final owns = switch (phase) {
      CapturePhase.idle || CapturePhase.callActive => false,
      _ => true,
    };
    if (owns && active == null) {
      throw const FormatException('Owning phase without a session');
    }
    if (!owns && active != null) {
      throw const FormatException('Non-owning phase with a session');
    }
    if (active != null) {
      final pendantPhase = phase == CapturePhase.pendantLive ||
          phase == CapturePhase.pendantPaused ||
          phase == CapturePhase.pendantBatchLive ||
          phase == CapturePhase.pendantBatchPaused;
      final expected = pendantPhase ? CaptureSource.pendant : CaptureSource.phone;
      if (active.source != expected) {
        throw const FormatException('Session source does not match phase');
      }
      final batchPhase = phase == CapturePhase.pendantBatchLive ||
          phase == CapturePhase.pendantBatchPaused ||
          phase == CapturePhase.phoneBatchLive ||
          phase == CapturePhase.phoneBatchPaused;
      final livePhase = phase == CapturePhase.pendantLive ||
          phase == CapturePhase.pendantPaused ||
          phase == CapturePhase.phoneLive ||
          phase == CapturePhase.phonePaused;
      if ((batchPhase && active.mode != CaptureTransport.batch) ||
          (livePhase && active.mode != CaptureTransport.live)) {
        throw const FormatException('Session mode does not match phase');
      }
    }

    return CaptureCoordinatorState(
      phase: phase,
      active: active,
      suspended: suspended,
      connectedDevice: connectedDevice,
      callActive: callActive,
      micInterrupted: micInterrupted,
      mutedBeforePhone: mutedBeforePhone,
      sessionSeq: sessionSeq,
      lastFailure: lastFailure,
    );
  }

  /// Parses a persisted snapshot. Returns null on every malformed or
  /// unsupported representation; the caller restores idle.
  static CaptureCoordinatorState? tryParse(String? encoded) {
    if (encoded == null || encoded.isEmpty) return null;
    try {
      final decoded = jsonDecode(encoded);
      if (decoded is! Map<String, dynamic>) return null;
      return CaptureCoordinatorState.fromJson(decoded);
    } on Object {
      return null;
    }
  }
}

CapturePhase _parsePhase(Object? value) {
  for (final phase in CapturePhase.values) {
    if (phase.name == value) return phase;
  }
  throw const FormatException('Unknown capture phase');
}

CaptureSource _parseSource(Object? value) {
  for (final source in CaptureSource.values) {
    if (source.name == value) return source;
  }
  throw const FormatException('Unknown capture source');
}

CaptureTransport _parseTransport(Object? value) {
  for (final mode in CaptureTransport.values) {
    if (mode.name == value) return mode;
  }
  throw const FormatException('Unknown capture transport');
}

SuspendReason _parseSuspendReason(Object? value) {
  for (final reason in SuspendReason.values) {
    if (reason.name == value) return reason;
  }
  throw const FormatException('Unknown suspend reason');
}

DeviceType? _parseDeviceType(Object? value) {
  if (value == null) return null;
  return _parseDeviceTypeRequired(value);
}

DeviceType _parseDeviceTypeRequired(Object? value) {
  for (final type in DeviceType.values) {
    if (type.name == value) return type;
  }
  throw const FormatException('Unknown device type');
}

String _parseString(Object? value, String field) {
  if (value is String && value.isNotEmpty) return value;
  throw FormatException('Missing $field');
}

bool _parseBool(Object? value, String field) {
  if (value is bool) return value;
  throw FormatException('Missing $field');
}

// ---------------------------------------------------------------------------
// Environment: the controller's view of the world, sampled when an event runs
// ---------------------------------------------------------------------------

/// Inputs the reducer needs that live outside coordinator state. Sampled once
/// per dequeued event so a queued event decides on the conditions at the
/// moment it runs, not when it was posted.
class CaptureEnvironment {
  const CaptureEnvironment({
    required this.policyMuted,
    required this.paused,
    required this.batchModeEnabled,
    required this.batchModeSuspendedForOnboarding,
    required this.deviceSupportsTranscribeLater,
    required this.networkConnected,
    required this.signedIn,
    required this.phoneMicSupportsBatch,
    required this.transcriptReady,
    required this.socketConnected,
    required this.deviceServiceReady,
    required this.callActive,
    required this.deviceRecording,
    required this.micCapturing,
    this.systemAudioRecording = false,
  });

  /// `_preferences.capturePolicy.muted`.
  final bool policyMuted;

  /// `_preferences.deviceMuted` — the user pause flag.
  final bool paused;

  final bool batchModeEnabled;
  final bool batchModeSuspendedForOnboarding;
  final bool deviceSupportsTranscribeLater;
  final bool networkConnected;
  final bool Function() signedIn;
  final bool phoneMicSupportsBatch;
  final bool transcriptReady;
  final bool socketConnected;

  /// `recordingDeviceServiceReady` — device present or a mic lane active.
  final bool deviceServiceReady;
  final bool callActive;

  /// `recordingState == deviceRecord`.
  final bool deviceRecording;

  /// `recordingState` in {record, interrupted, systemAudioRecord}.
  final bool micCapturing;
  final bool systemAudioRecording;

  /// Mirrors [selectPhoneMicSessionMode] so the reducer can phase the session
  /// before the start effect picks the same mode.
  CaptureTransport phoneTransport() {
    if (!phoneMicSupportsBatch) return CaptureTransport.live;
    if (batchModeEnabled) return CaptureTransport.batch;
    if (!networkConnected) return CaptureTransport.batch;
    return CaptureTransport.live;
  }
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

sealed class CaptureEvent {
  const CaptureEvent();
}

/// `streamRecording`. [resumePolicy] mirrors the resumeCapture argument: an
/// explicit start unmutes and captures the pre-start policy for restore.
class PhoneStartRequested extends CaptureEvent {
  const PhoneStartRequested({this.resumePolicy = true});
  final bool resumePolicy;
}

/// `stopStreamRecording`. [userStop] selects the user-stop policy restore;
/// [resumeSuspendedPendant] maps resumeHandedOffPendant.
class PhoneStopRequested extends CaptureEvent {
  const PhoneStopRequested({
    required this.reason,
    required this.userStop,
    this.resumeSuspendedPendant = true,
  });
  final String reason;
  final bool userStop;
  final bool resumeSuspendedPendant;
}

/// `finishCapture`: stop and process the phone conversation before a pendant
/// it took over from resumes.
class FinishRequested extends CaptureEvent {
  const FinishRequested();
}

/// `pauseCapture`: pause whichever source currently owns capture.
class PauseCaptureRequested extends CaptureEvent {
  const PauseCaptureRequested();
}

/// `resumeCapture`: resume the source pause paused.
class ResumeCaptureRequested extends CaptureEvent {
  const ResumeCaptureRequested();
}

/// `toggleOfflineMute`.
class OfflineMuteToggled extends CaptureEvent {
  const OfflineMuteToggled();
}

/// `streamDeviceRecording(device:)` — a pendant start or a check-only entry.
/// The [BtDevice] is carried for the stage body; the reducer stores only its
/// identity in state.
class DeviceStartRequested extends CaptureEvent {
  const DeviceStartRequested({this.device});
  final BtDevice? device;
}

/// `stopStreamDeviceRecording`.
class DeviceStopRequested extends CaptureEvent {
  const DeviceStopRequested({this.cleanDevice = false});
  final bool cleanDevice;
}

/// `updateRecordingDevice` — connect, disconnect (null), or identity update.
class DeviceUpdated extends CaptureEvent {
  const DeviceUpdated(this.device);
  final BtDevice? device;
}

/// `startPhoneMicBatchForTesting` — a direct batch start without the
/// `streamRecording` prelude.
class PhoneBatchStartRequested extends CaptureEvent {
  const PhoneBatchStartRequested({this.auto = false});
  final bool auto;
}

/// `pauseDeviceRecording` / `resumeDeviceRecording`.
class DevicePauseRequested extends CaptureEvent {
  const DevicePauseRequested();
}

class DeviceResumeRequested extends CaptureEvent {
  const DeviceResumeRequested();
}

/// `_onOmiCallStateChanged` — the reducer re-reads the call state from the
/// environment at run time like the queued switch did.
class CallStateChanged extends CaptureEvent {
  const CallStateChanged();
}

/// `_onMicInterruption`.
class MicInterruptionChanged extends CaptureEvent {
  const MicInterruptionChanged({required this.began});
  final bool began;
}

/// `_onMicStalled` / `_onBatchStalled` — the reducer picks the lane.
class NativeMicStalled extends CaptureEvent {
  const NativeMicStalled();
}

/// `onAppResumed`.
class AppForegrounded extends CaptureEvent {
  const AppForegrounded();
}

/// Socket listener callbacks.
class SocketClosed extends CaptureEvent {
  const SocketClosed({this.closeCode});
  final int? closeCode;
}

class SocketConnected extends CaptureEvent {
  const SocketConnected();
}

class SocketError extends CaptureEvent {
  const SocketError(this.error);
  final Object error;
}

/// The keep-alive periodic reached its reconnect branch.
class KeepAliveTick extends CaptureEvent {
  const KeepAliveTick({this.testingProbe = false});
  final bool testingProbe;
}

/// `setBatchMode`. The stage returns the accepted flag.
class BatchModeSetRequested extends CaptureEvent {
  const BatchModeSetRequested({required this.enabled});
  final bool enabled;
}

/// `onTranscriptionSettingsChanged`.
class TranscriptionSettingsChanged extends CaptureEvent {
  const TranscriptionSettingsChanged();
}

/// `onRecordProfileSettingChanged`.
class RecordProfileChanged extends CaptureEvent {
  const RecordProfileChanged();
}

/// `suspendBatchModeForOnboarding` / `restoreBatchModeAfterOnboarding`.
class OnboardingBatchChanged extends CaptureEvent {
  const OnboardingBatchChanged({required this.suspended});
  final bool suspended;
}

/// `_recoverPhoneRestoreMarker` — a phone recording left its policy intent
/// persisted across a process boundary; restore it.
class LaunchRecovery extends CaptureEvent {
  const LaunchRecovery({required this.markerPending, required this.mutedBefore});
  final bool markerPending;
  final bool mutedBefore;
}

// ---------------------------------------------------------------------------
// Effects
// ---------------------------------------------------------------------------

sealed class CaptureEffect {
  const CaptureEffect();
}

/// Write the shared capture policy (CAPTURE_POLICY.md). The port returns the
/// committed revision and whether a newer intent superseded this write.
class PolicyWrite extends CaptureEffect {
  const PolicyWrite(this.muted);
  final bool muted;
}

/// Stop the pendant's Dart BLE stream (and optionally the native background
/// route) — `_closeBleStream`.
class BleStreamStop extends CaptureEffect {
  const BleStreamStop({this.disableNativeBackground = false});
  final bool disableNativeBackground;
}

/// (Re)open the pendant's Dart BLE stream — `_initiateDeviceAudioStreaming`.
class BleStreamStart extends CaptureEffect {
  const BleStreamStart();
}

/// Open the transcription socket. [ensureOnly] skips the open when the socket
/// is already connected (phone resume). Config mirrors `_initiateWebsocket`.
class SocketOpen extends CaptureEffect {
  const SocketOpen({
    required this.codec,
    required this.sampleRate,
    this.force = false,
    this.source,
    this.ensureOnly = false,
  });
  final BleAudioCodec codec;
  final int sampleRate;
  final bool force;
  final String? source;
  final bool ensureOnly;
}

class SocketClose extends CaptureEffect {
  const SocketClose(this.reason);
  final String reason;
}

/// Native phone mic start for a transport: live resumes the existing mic
/// recording; batch starts a native .bin session.
class NativeMicStart extends CaptureEffect {
  const NativeMicStart(this.mode);
  final PhoneMicSessionMode mode;
}

class NativeMicStop extends CaptureEffect {
  const NativeMicStop();
}

/// Per-source native writer gate. Interface only — no native implementation
/// exists yet; batch pendant↔phone handoff stays refused until this lands.
class NativeWriterGate extends CaptureEffect {
  const NativeWriterGate({required this.source, required this.admitted});
  final CaptureSource source;
  final bool admitted;
}

/// Drain the in-memory WAL tail to disk.
class WalFinalize extends CaptureEffect {
  const WalFinalize();
}

/// Roll the capture session identity at a WAL/session boundary.
class WalSessionRoll extends CaptureEffect {
  const WalSessionRoll(this.identity);
  final String identity;
}

/// Mint the recording id for a fresh session. The port returns the id, which
/// the dispatcher folds into the committed active session.
class MintRecording extends CaptureEffect {
  const MintRecording({required this.sessionKey, required this.telemetrySource});
  final String sessionKey;
  final String telemetrySource;
}

/// Run a migrated composite transition body on the controller (the staged
/// migration seam — see CAPTURE_ARCHITECTURE.md).
class RunStage extends CaptureEffect {
  const RunStage(this.stage);
  final CaptureStage stage;
}

// ---------------------------------------------------------------------------
// Stages — composite bodies still owned by the controller
// ---------------------------------------------------------------------------

sealed class CaptureStage {
  const CaptureStage();
}

class UpdateRecordingDeviceStage extends CaptureStage {
  const UpdateRecordingDeviceStage(this.device);
  final BtDevice? device;
}

/// `streamDeviceRecording` after the owner check: session roll, location,
/// reset and streaming init. [promptLocation] mirrors the old
/// `promptIfDenied: device != null`.
class StartDeviceSessionStage extends CaptureStage {
  const StartDeviceSessionStage({required this.deviceRequested, this.promptLocation = false});
  final bool deviceRequested;
  final bool promptLocation;
}

class StopDeviceSessionStage extends CaptureStage {
  const StopDeviceSessionStage({required this.cleanDevice});
  final bool cleanDevice;
}

/// Post-mute tail of `pauseDeviceRecording`.
class PauseDeviceTailStage extends CaptureStage {
  const PauseDeviceTailStage();
}

/// Post-unmute tail of `resumeDeviceRecording`.
class ResumeDeviceTailStage extends CaptureStage {
  const ResumeDeviceTailStage();
}

/// `_handOffPendant`: close the pendant's stream; for the phone reason also
/// process its conversation and close its recording.
class SuspendPendantStage extends CaptureStage {
  const SuspendPendantStage({required this.reason, required this.wasPaused});
  final SuspendReason reason;
  final bool wasPaused;
}

/// A pendant paused for a call gets taken by the phone instead: its recording
/// ends here and it comes back when the phone finishes.
class ConvertCallSuspensionStage extends CaptureStage {
  const ConvertCallSuspensionStage();
}

/// Call-resume tail: restore the suspended pendant in the state it was in.
class ResumeSuspendedPendantStage extends CaptureStage {
  const ResumeSuspendedPendantStage({required this.wasPaused});
  final bool wasPaused;
}

/// `streamRecording` after admission bookkeeping: marker/unmute already ran
/// as effects; this runs the session tail.
class StartPhoneSessionStage extends CaptureStage {
  const StartPhoneSessionStage({required this.mode});
  final CaptureTransport mode;
}

/// Persisted while a phone recording is live so a process death cannot leave
/// the next launch muted.
class WritePhoneRestoreMarkerStage extends CaptureStage {
  const WritePhoneRestoreMarkerStage({required this.mutedBefore});
  final bool mutedBefore;
}

class ClearPhoneRestoreMarkerStage extends CaptureStage {
  const ClearPhoneRestoreMarkerStage();
}

/// Live phone teardown (`stopStreamRecording` non-batch tail).
class StopPhoneLiveStage extends CaptureStage {
  const StopPhoneLiveStage({required this.reason});
  final String reason;
}

/// Batch phone teardown.
class StopPhoneBatchStage extends CaptureStage {
  const StopPhoneBatchStage({required this.reason});
  final String reason;
}

/// Conditional post-stop policy restore:
/// `if (!pendantResumeFollows && mutedBefore == false && isPaused) unmute`.
class StopPhonePolicyRestoreStage extends CaptureStage {
  const StopPhonePolicyRestoreStage({
    required this.mutedBefore,
    required this.pendantResumeFollows,
    required this.userStop,
  });
  final bool? mutedBefore;
  final bool pendantResumeFollows;
  final bool userStop;
}

/// Flush buffered phone frames to the WAL/socket before the mic releases.
class FlushPhoneFramesStage extends CaptureStage {
  const FlushPhoneFramesStage();
}

/// `updateRecordingState(state)` — a recording-state mark that rode along
/// inside a composite body.
class RecordingMarkStage extends CaptureStage {
  const RecordingMarkStage(this.state);
  final RecordingState state;
}

/// Teardown-only tail of `stopStreamDeviceRecording` (before the socket
/// close): roll, cleanup, WAL finalize, clean-device, stop mark, keepalive.
class DeviceStopTelemetryStage extends CaptureStage {
  const DeviceStopTelemetryStage({required this.cleanDevice});
  final bool cleanDevice;
}

/// `forceProcessingCurrentConversation` plus the in-flight join.
class ProcessConversationStage extends CaptureStage {
  const ProcessConversationStage();
}

class SocketClosedStage extends CaptureStage {
  const SocketClosedStage({this.closeCode});
  final int? closeCode;
}

class SocketConnectedStage extends CaptureStage {
  const SocketConnectedStage();
}

class SocketErrorStage extends CaptureStage {
  const SocketErrorStage(this.error);
  final Object error;
}

/// The reconnect branch of the keep-alive tick.
class ReconnectDeviceStage extends CaptureStage {
  const ReconnectDeviceStage();
}

class ReconnectPhoneStage extends CaptureStage {
  const ReconnectPhoneStage();
}

class MicInterruptionStage extends CaptureStage {
  const MicInterruptionStage({required this.began});
  final bool began;
}

/// `_onMicStalled` escalation for the live lane.
class RestartLiveMicStage extends CaptureStage {
  const RestartLiveMicStage();
}

/// `_onBatchStalled` watchdog escalation for the batch lane.
class RestartBatchMicStage extends CaptureStage {
  const RestartBatchMicStage();
}

/// `onAppResumed`: soft-rearm the stall clock.
class ProbeStallStage extends CaptureStage {
  const ProbeStallStage();
}

/// `setBatchMode` — returns the accepted bool. [rolledPhoneMode] is the
/// pre-transition mode of a live phone session that must roll into the new
/// mode (the reducer commits the new phase before the body runs).
class BatchModeStage extends CaptureStage {
  const BatchModeStage({required this.enabled, this.rolledPhoneMode});
  final bool enabled;
  final CaptureTransport? rolledPhoneMode;
}

class TranscriptionSettingsStage extends CaptureStage {
  const TranscriptionSettingsStage();
}

/// `onRecordProfileSettingChanged` → `_resetState`.
class RecordProfileStage extends CaptureStage {
  const RecordProfileStage();
}

/// Speech-profile / onboarding batch suspend or restore.
class OnboardingBatchStage extends CaptureStage {
  const OnboardingBatchStage({required this.suspended});
  final bool suspended;
}

/// `startPhoneMicBatchForTesting`-equivalent direct batch start.
class StartPhoneBatchStage extends CaptureStage {
  const StartPhoneBatchStage({required this.auto});
  final bool auto;
}

// ---------------------------------------------------------------------------
// Ports — the narrow injectable effect boundary
// ---------------------------------------------------------------------------

/// Result of a policy write through the port.
class PolicyWriteOutcome {
  const PolicyWriteOutcome({required this.revision, required this.superseded});
  final int revision;

  /// A newer intent landed after this write was admitted; the dispatcher
  /// abandons the rest of the effect list for this event.
  final bool superseded;
}

typedef CapturePolicyWriter = Future<PolicyWriteOutcome> Function(bool muted);

/// Per-source native writer gate — interface only until a native
/// implementation exists; batch handoffs stay refused meanwhile.
abstract interface class CaptureNativeWriterGate {
  Future<void> setGate(CaptureSource source, bool admitted);
}

class NoopCaptureNativeWriterGate implements CaptureNativeWriterGate {
  const NoopCaptureNativeWriterGate();
  @override
  Future<void> setGate(CaptureSource source, bool admitted) async {}
}

/// Every I/O the coordinator may order, one method per primitive; production
/// wires these to the controller's existing helpers, tests inject fakes.
class CaptureEffectPorts {
  const CaptureEffectPorts({
    required this.writePolicy,
    required this.stopBleStream,
    required this.startBleStream,
    required this.openSocket,
    required this.closeSocket,
    required this.startNativeMic,
    required this.stopNativeMic,
    required this.setNativeWriterGate,
    required this.finalizeWal,
    required this.rollSession,
    required this.mintRecordingId,
    required this.currentRecordingId,
    required this.readSnapshot,
    required this.persistSnapshot,
    required this.runStage,
  });

  /// `_setCaptureMuted` — the durable admission write.
  final CapturePolicyWriter writePolicy;

  /// `_closeBleStream`.
  final Future<void> Function({bool disableNativeBackground}) stopBleStream;

  /// `_initiateDeviceAudioStreaming`.
  final Future<void> Function() startBleStream;

  /// `_initiateWebsocket` (ensure-aware).
  final Future<void> Function(SocketOpen spec) openSocket;

  /// `_socket?.stop(reason:)`.
  final Future<void> Function(String reason) closeSocket;

  /// Live: `_resumeMicRecording`; batch: `_startPhoneMicBatch`.
  final Future<void> Function(PhoneMicSessionMode mode) startNativeMic;

  /// `_phoneMic.stop()`.
  final Future<void> Function() stopNativeMic;

  /// Per-source native writer gate — interface only, no native backend yet.
  final Future<void> Function(CaptureSource source, bool admitted) setNativeWriterGate;

  /// `_wal.getSyncs().phone.finalizeCurrentSession()`.
  final Future<void> Function() finalizeWal;

  /// `_rollCaptureSession(identity)` at a WAL/session boundary.
  final Future<void> Function(String identity) rollSession;

  /// `_recordingTelemetry.prepare(source:)` returning the recording id.
  final String Function(String sessionKey, String telemetrySource) mintRecordingId;

  /// The telemetry's current recording id — folds ids minted inside stages
  /// (session rolls) back into the committed active session after a dispatch.
  final String? Function() currentRecordingId;

  /// Durable snapshot read/write (last step of a safe transition).
  final String? Function() readSnapshot;
  final Future<void> Function(String encoded) persistSnapshot;

  /// The migrated composite bodies.
  final Future<Object?> Function(CaptureStage stage) runStage;
}

// ---------------------------------------------------------------------------
// Read model — the derived view consumed by controller getters
// ---------------------------------------------------------------------------

/// The one derived read-model over committed state. Controller getters and the
/// `liveCaptureDisplayState` inputs read this — never the reducer internals.
class CaptureReadModel {
  const CaptureReadModel(this.state);
  final CaptureCoordinatorState state;

  CapturePhase get phase => state.phase;
  bool get phoneOwnsCapture => state.phoneOwns;
  bool get pendantOwns => state.pendantOwns;
  bool get phonePaused => state.phase == CapturePhase.phonePaused;
  bool get phoneBatchActive =>
      state.phase == CapturePhase.phoneBatchLive || state.phase == CapturePhase.phoneBatchPaused;
  bool get micInterrupted => state.micInterrupted;
  bool get callActive => state.callActive;
  ConnectedDevice? get connectedDevice => state.connectedDevice;
  SuspendedCapture? get pendantSuspension => state.pendantSuspension;
  bool get pendantSuspendedForPhone => pendantSuspension?.reason == SuspendReason.phone;
  bool get pendantSuspendedForCall => pendantSuspension?.reason == SuspendReason.call;
  bool get pendantHoldsCapture => state.pendantHoldsCapture;
  String? get activeRecordingId => state.active?.recordingId;

  /// A phone Transcribe Later session exists (running or paused or interrupted):
  /// the native writer owns its file regardless of the momentary phase.
  bool get phoneBatchSession => state.phoneOwns && state.active?.mode == CaptureTransport.batch;

  /// `liveCaptureSource` inputs: 'phone' while the phone owns, the pendant's
  /// conversation source while it owns, null otherwise.
  String? get liveOwnerName => switch (phase) {
        CapturePhase.phoneLive ||
        CapturePhase.phonePaused ||
        CapturePhase.phoneBatchLive ||
        CapturePhase.phoneBatchPaused ||
        CapturePhase.audioInterrupted =>
          'phone',
        CapturePhase.pendantLive ||
        CapturePhase.pendantPaused ||
        CapturePhase.pendantBatchLive ||
        CapturePhase.pendantBatchPaused =>
          'pendant',
        _ => null,
      };

  /// Inputs for `liveCaptureDisplayState` — an interruption or any paused
  /// phase reports paused; a pendant pause is the device mute.
  bool get audioInterrupted => state.micInterrupted;

  bool get paused => switch (phase) {
        CapturePhase.pendantPaused ||
        CapturePhase.pendantBatchPaused ||
        CapturePhase.phonePaused ||
        CapturePhase.phoneBatchPaused =>
          true,
        _ => false,
      };

  bool get deviceMuted => state.phase == CapturePhase.pendantPaused || state.phase == CapturePhase.pendantBatchPaused;
}

// ---------------------------------------------------------------------------
// Dispatch outcome
// ---------------------------------------------------------------------------

class CaptureDispatchOutcome {
  const CaptureDispatchOutcome._({
    required this.admitted,
    required this.state,
    this.result,
    this.error,
    this.stackTrace,
    this.absorbed = false,
  });

  factory CaptureDispatchOutcome.denied(CaptureCoordinatorState state) =>
      CaptureDispatchOutcome._(admitted: false, state: state);

  factory CaptureDispatchOutcome.completed({
    required CaptureCoordinatorState state,
    Object? result,
    Object? error,
    StackTrace? stackTrace,
    bool absorbed = false,
  }) =>
      CaptureDispatchOutcome._(
        admitted: true,
        state: state,
        result: result,
        error: error,
        stackTrace: stackTrace,
        absorbed: absorbed,
      );

  /// False when the coordinator is disposed: the event was refused.
  final bool admitted;

  /// Committed state after the run — the fail-closed form on effect failure.
  final CaptureCoordinatorState state;

  /// Last non-null stage result (e.g. setBatchMode's acceptance).
  final Object? result;

  /// Effect failure, if any. [absorbed] marks failures a stage converted to
  /// its legacy user-visible path (e.g. a failed mic start that ends the
  /// session instead of throwing to the caller).
  final Object? error;
  final StackTrace? stackTrace;
  final bool absorbed;

  bool get failed => error != null;

  /// Propagate a non-absorbed failure to the caller the way the unqueued
  /// implementation would have thrown it.
  void throwIfFailed() {
    if (error != null && !absorbed) {
      Error.throwWithStackTrace(error!, stackTrace ?? StackTrace.current);
    }
  }
}

/// A stage converts a start/teardown failure into its legacy visible path and
/// returns this marker instead of throwing: the transition still fails closed
/// in state, while the caller sees the historical non-throwing completion.
class CaptureStageFailure {
  const CaptureStageFailure(this.error, {this.absorbed = true});
  final Object error;
  final bool absorbed;
}

// ---------------------------------------------------------------------------
// Transition
// ---------------------------------------------------------------------------

class CaptureTransition {
  CaptureTransition(this.state, List<CaptureEffect> effects) : effects = List.unmodifiable(effects);
  final CaptureCoordinatorState state;
  final List<CaptureEffect> effects;
}

// ---------------------------------------------------------------------------
// Coordinator
// ---------------------------------------------------------------------------

class CaptureCoordinator {
  CaptureCoordinator({
    required CaptureEffectPorts ports,
    required CaptureEnvironment Function() readEnvironment,
    void Function(CaptureCoordinatorState state)? onCommit,
  })  : _ports = ports,
        _readEnvironment = readEnvironment,
        _onCommit = onCommit {
    final restored = CaptureCoordinatorState.tryParse(_ports.readSnapshot());
    _state = restored?.sanitizedForLaunch() ?? CaptureCoordinatorState.idle();
  }

  final CaptureEffectPorts _ports;
  final CaptureEnvironment Function() _readEnvironment;
  final void Function(CaptureCoordinatorState state)? _onCommit;

  late CaptureCoordinatorState _state;
  CaptureCoordinatorState? _staged;

  final List<({CaptureEvent event, Completer<CaptureDispatchOutcome> done})> _queue = [];
  bool _running = false;
  bool _disposed = false;
  Completer<void>? _drain;
  Future<CaptureDispatchOutcome>? _testingProbe;

  CaptureCoordinatorState get state => _state;
  CaptureReadModel get readModel => CaptureReadModel(_state);

  /// The staged view effect bodies see mid-transition: the unpublished target
  /// (plus folds) while effects run, the committed state otherwise. Published
  /// ownership only advances to the target after its effects complete safely.
  CaptureReadModel get stagedReadModel => CaptureReadModel(_staged ?? _state);

  /// Completes when every queued event has run. Mirrors the old
  /// `pendingSourceSwitch` contract for the call-switch tests.
  Future<void> get pendingDrain => _drain?.future ?? Future<void>.value();

  /// Serialized FIFO admission. Awaits the event's full effect list, so the
  /// returned outcome only exists after the transition is safely committed —
  /// or after it failed closed with the error attached.
  Future<CaptureDispatchOutcome> dispatch(CaptureEvent event) {
    if (_disposed) {
      return Future<CaptureDispatchOutcome>.value(CaptureDispatchOutcome.denied(_state));
    }
    if (event is KeepAliveTick && event.testingProbe && _testingProbe != null) return _testingProbe!;
    final done = Completer<CaptureDispatchOutcome>();
    if (event is KeepAliveTick && event.testingProbe) _testingProbe = done.future;
    _queue.add((event: event, done: done));
    _drain ??= Completer<void>();
    _pump();
    return done.future;
  }

  /// Deny new dispatches; in-flight effects drain on their own.
  void dispose() {
    _disposed = true;
  }

  void _pump() {
    if (_running) return;
    _running = true;
    () async {
      try {
        while (_queue.isNotEmpty && !_disposed) {
          final item = _queue.removeAt(0);
          try {
            final outcome = await _run(item.event);
            if (!item.done.isCompleted) item.done.complete(outcome);
          } catch (error, stack) {
            if (!item.done.isCompleted) {
              item.done.complete(CaptureDispatchOutcome.completed(
                state: _state,
                error: error,
                stackTrace: stack,
              ));
            }
          } finally {
            if (item.event is KeepAliveTick && (item.event as KeepAliveTick).testingProbe) _testingProbe = null;
          }
        }
      } finally {
        _running = false;
        if (_queue.isEmpty) {
          _drain?.complete();
          _drain = null;
        } else {
          // Dispose cleared the run loop; refuse what is left queued.
          final denied = List.of(_queue);
          _queue.clear();
          for (final item in denied) {
            if (!item.done.isCompleted) {
              item.done.complete(CaptureDispatchOutcome.denied(_state));
            }
          }
          _drain?.complete();
          _drain = null;
        }
      }
    }();
  }

  Future<CaptureDispatchOutcome> _run(CaptureEvent event) async {
    final CaptureTransition transition;
    try {
      transition = transitionCapture(_state, event, _readEnvironment());
    } catch (error, stack) {
      // Nothing physical could have started; keep the committed state.
      return CaptureDispatchOutcome.completed(state: _state, error: error, stackTrace: stack);
    }
    var working = transition.state;
    _staged = working;

    try {
      Object? result;
      for (var i = 0; i < transition.effects.length; i++) {
        try {
          final value = await _execute(transition.effects[i]);
          if (value is _MintedRecordingId) {
            working = _foldMintedId(working, value);
            _staged = working;
          } else if (value is PolicyWriteOutcome) {
            if (value.superseded) {
              if (i == 0) {
                return CaptureDispatchOutcome.completed(state: _state, result: false);
              }
              return _failClosed(working, StateError('capture transition superseded by a newer capture intent'));
            }
          } else if (value is CaptureStageFailure) {
            return _failClosed(working, value.error, absorbed: value.absorbed);
          } else if (value != null) {
            result = value;
          }
        } catch (error, stack) {
          return _failClosed(working, error, stackTrace: stack);
        }
      }

      final active = working.active;
      final telemetryId = _ports.currentRecordingId();
      if (active != null && telemetryId != null && active.recordingId != telemetryId) {
        working = working.copyWith(active: () => active.copyWith(recordingId: telemetryId));
        _staged = working;
      }

      // Required durability is part of the safe transition: a failed snapshot
      // write fails closed like any other effect failure, before publish.
      await _ports.persistSnapshot(working.encode());
      _commit(working);
      return CaptureDispatchOutcome.completed(state: _state, result: result);
    } catch (error, stack) {
      return _failClosed(working, error, stackTrace: stack);
    } finally {
      _staged = null;
    }
  }

  /// The transition failed after committing to state: physical capture is
  /// denied best-effort before the safe idle form is published, and the
  /// original error reaches the caller.
  Future<CaptureDispatchOutcome> _failClosed(CaptureCoordinatorState working, Object error,
      {StackTrace? stackTrace, bool absorbed = false}) async {
    for (final deny in [
      () => _ports.setNativeWriterGate(CaptureSource.pendant, false),
      () => _ports.setNativeWriterGate(CaptureSource.phone, false),
      () => _ports.stopNativeMic(),
      () => _ports.stopBleStream(disableNativeBackground: true),
      () => _ports.closeSocket('capture transition failed'),
    ]) {
      try {
        await deny();
      } catch (_) {}
    }
    final closed = working.failedClosed(error);
    _staged = closed;
    _commit(closed);
    try {
      await _ports.persistSnapshot(_state.encode());
    } catch (_) {}
    return CaptureDispatchOutcome.completed(
      state: _state,
      error: error,
      stackTrace: stackTrace,
      absorbed: absorbed,
    );
  }

  void _commit(CaptureCoordinatorState next) {
    _state = next;
    _onCommit?.call(next);
  }

  CaptureCoordinatorState _foldMintedId(CaptureCoordinatorState working, _MintedRecordingId minted) {
    final active = working.active;
    if (active == null || active.sessionKey != minted.sessionKey) return working;
    return working.copyWith(active: () => active.copyWith(recordingId: minted.recordingId));
  }

  Future<Object?> _execute(CaptureEffect effect) => switch (effect) {
        PolicyWrite() => _ports.writePolicy(effect.muted),
        BleStreamStop() => _ports.stopBleStream(disableNativeBackground: effect.disableNativeBackground),
        BleStreamStart() => _ports.startBleStream(),
        SocketOpen() => _ports.openSocket(effect),
        SocketClose() => _ports.closeSocket(effect.reason),
        NativeMicStart() => _ports.startNativeMic(effect.mode),
        NativeMicStop() => _ports.stopNativeMic(),
        NativeWriterGate() => _ports.setNativeWriterGate(effect.source, effect.admitted),
        WalFinalize() => _ports.finalizeWal(),
        WalSessionRoll() => _ports.rollSession(effect.identity),
        MintRecording() => Future<_MintedRecordingId>.value(
            _MintedRecordingId(effect.sessionKey, _ports.mintRecordingId(effect.sessionKey, effect.telemetrySource)),
          ),
        RunStage() => _ports.runStage(effect.stage),
      };
}

// -------------------------------------------------------------------------
// Reducer — pure: (state, event, env) -> (next state, ordered effects)
// -------------------------------------------------------------------------

CaptureTransition transitionCapture(CaptureCoordinatorState state, CaptureEvent event, CaptureEnvironment env) =>
    switch (event) {
      PhoneStartRequested() => _reducePhoneStart(state, event, env),
      PhoneStopRequested() => _reducePhoneStop(state, event),
      FinishRequested() => _reduceFinish(state),
      PauseCaptureRequested() => _reducePause(state, env),
      ResumeCaptureRequested() => _reduceResume(state, env),
      OfflineMuteToggled() => _reduceOfflineMuteToggle(state, env),
      DeviceStartRequested() => _reduceDeviceStart(state, event, env),
      DeviceStopRequested() => _reduceDeviceStop(state, event),
      DeviceUpdated() => _reduceDeviceUpdated(state, event),
      PhoneBatchStartRequested() => _reducePhoneBatchStart(state, event),
      DevicePauseRequested() => _reduceDevicePause(state, env),
      DeviceResumeRequested() => _reduceDeviceResume(state, env),
      CallStateChanged() => _reduceCall(state, env),
      MicInterruptionChanged() => _reduceMicInterruption(state, event),
      NativeMicStalled() => _reduceMicStalled(state),
      AppForegrounded() => _reduceAppForegrounded(state),
      SocketClosed() => CaptureTransition(state, [RunStage(SocketClosedStage(closeCode: event.closeCode))]),
      SocketConnected() => CaptureTransition(state, const [RunStage(SocketConnectedStage())]),
      SocketError() => CaptureTransition(state, [RunStage(SocketErrorStage(event.error))]),
      KeepAliveTick() => _reduceKeepAlive(state, event, env),
      BatchModeSetRequested() => _reduceBatchMode(state, event, env),
      TranscriptionSettingsChanged() => CaptureTransition(state, const [RunStage(TranscriptionSettingsStage())]),
      RecordProfileChanged() => CaptureTransition(state, const [RunStage(RecordProfileStage())]),
      OnboardingBatchChanged() => _reduceOnboardingBatch(state, event),
      LaunchRecovery() => _reduceLaunchRecovery(state, event, env),
    };

CaptureTransition _reducePhoneStart(CaptureCoordinatorState state, PhoneStartRequested event, CaptureEnvironment env) {
  // An explicit restart rolls the old phone session before minting a new id;
  // socket recovery uses its own events and never rolls the conversation.
  // A batch pendant's native writer owns its file under the shared policy; no
  // per-source gate exists to deny it, so the takeover is refused outright.
  if (state.phase == CapturePhase.pendantBatchLive ||
      state.phase == CapturePhase.pendantBatchPaused ||
      state.pendantSuspension?.mode == CaptureTransport.batch) {
    return CaptureTransition(state, const []);
  }
  // resumePolicy:false leaves the shared policy as it stands; under a muted
  // policy the mic body would refuse admission, so reject before minting or
  // suspending rather than publish an owner no physical effect can open.
  if (!event.resumePolicy && env.policyMuted) {
    return CaptureTransition(state, const []);
  }
  final mode = env.phoneTransport();
  final seq = state.sessionSeq + 1;
  final key = 'phone-$seq';
  final mutedBefore = event.resumePolicy ? (state.mutedBeforePhone ?? env.paused) : state.mutedBeforePhone;
  final suspended = List<SuspendedCapture>.of(state.suspended);
  final effects = <CaptureEffect>[
    if (state.phoneOwns)
      RunStage(state.active?.mode == CaptureTransport.batch
          ? const StopPhoneBatchStage(reason: 'source_restarted')
          : const StopPhoneLiveStage(reason: 'source_restarted')),
  ];

  if (state.pendantHoldsCapture) {
    // The pendant hands off: its conversation ends here and it resumes when
    // this recording stops.
    final wasPaused = state.phase == CapturePhase.pendantPaused;
    suspended.add(SuspendedCapture(
      source: CaptureSource.pendant,
      reason: SuspendReason.phone,
      wasPaused: wasPaused,
      mode: state.active?.mode ?? CaptureTransport.live,
      sessionKey: state.active?.sessionKey,
      recordingId: state.active?.recordingId,
      deviceId: state.active?.deviceId ?? state.connectedDevice?.id,
      deviceType: state.active?.deviceType ?? state.connectedDevice?.type,
    ));
    effects
      ..add(const NativeWriterGate(source: CaptureSource.pendant, admitted: false))
      ..add(const BleStreamStop(disableNativeBackground: true))
      ..add(RunStage(SuspendPendantStage(reason: SuspendReason.phone, wasPaused: wasPaused)));
  } else if (!state.phoneOwns && state.pendantSuspension?.reason == SuspendReason.call) {
    // The phone takes over from a pendant already paused for a call: the
    // pendant's recording ends here and it comes back when the phone
    // finishes, not when the call ends.
    final index = suspended.lastIndexWhere((e) => e.source == CaptureSource.pendant);
    suspended[index] = suspended[index].withReason(SuspendReason.phone);
    effects.add(const RunStage(ConvertCallSuspensionStage()));
  }

  if (event.resumePolicy) {
    effects.add(RunStage(WritePhoneRestoreMarkerStage(mutedBefore: mutedBefore ?? false)));
    effects.add(const PolicyWrite(false));
  }
  effects
    ..add(MintRecording(
      sessionKey: key,
      telemetrySource: switch (mode) {
        CaptureTransport.batch => env.batchModeEnabled ? 'phone_mic_batch' : 'phone_mic_batch_auto',
        CaptureTransport.live => 'phone_mic_live',
      },
    ))
    ..add(RunStage(StartPhoneSessionStage(mode: mode)));

  final next = state.copyWith(
    phase: mode == CaptureTransport.live ? CapturePhase.phoneLive : CapturePhase.phoneBatchLive,
    active: () => ActiveCaptureSession(source: CaptureSource.phone, mode: mode, sessionKey: key),
    suspended: suspended,
    mutedBeforePhone: () => mutedBefore,
    micInterrupted: false,
    sessionSeq: seq,
    lastFailure: () => null,
  );
  return CaptureTransition(next, effects);
}

CapturePhase _pendantResumePhase(CaptureTransport mode, bool wasPaused) => switch ((mode, wasPaused)) {
      (CaptureTransport.batch, true) => CapturePhase.pendantBatchPaused,
      (CaptureTransport.batch, false) => CapturePhase.pendantBatchLive,
      (_, true) => CapturePhase.pendantPaused,
      (_, false) => CapturePhase.pendantLive,
    };

CaptureTransition _reducePhoneStop(CaptureCoordinatorState state, PhoneStopRequested event) {
  if (!state.phoneOwns) {
    // An unowned phone stop must not tear down a pendant or a call's capture.
    return CaptureTransition(state, const []);
  }
  final effects = <CaptureEffect>[];
  final suspended = List<SuspendedCapture>.of(state.suspended);
  final mutedBefore = event.userStop ? state.mutedBeforePhone : null;

  if (event.userStop) effects.add(const PolicyWrite(true));

  final pendantSuspension = state.pendantSuspension;

  if (state.phase == CapturePhase.phoneBatchLive || state.phase == CapturePhase.phoneBatchPaused) {
    effects.add(RunStage(StopPhoneBatchStage(reason: event.reason)));
  } else {
    effects.add(RunStage(StopPhoneLiveStage(reason: event.reason)));
  }

  if (state.callActive) {
    // The call keeps the channel: no pendant resume and no shared-policy
    // restore until the call ends. A phone-suspended pendant becomes a call
    // suspension with its conversation already ended by the takeover, so its
    // session identity is cleared and the call-end resume mints fresh.
    if (pendantSuspension != null && pendantSuspension.reason == SuspendReason.phone) {
      suspended.remove(pendantSuspension);
      suspended.add(SuspendedCapture(
        source: CaptureSource.pendant,
        reason: SuspendReason.call,
        wasPaused: pendantSuspension.wasPaused,
        mode: pendantSuspension.mode,
        deviceId: pendantSuspension.deviceId ?? state.connectedDevice?.id,
        deviceType: pendantSuspension.deviceType ?? state.connectedDevice?.type,
      ));
    }
    return CaptureTransition(
      state.copyWith(
        phase: CapturePhase.callActive,
        active: () => null,
        suspended: suspended,
        // The deferred policy restore lands when the call ends.
        micInterrupted: false,
      ),
      effects,
    );
  }

  final resumePendant =
      event.userStop && pendantSuspension?.reason == SuspendReason.phone && event.resumeSuspendedPendant;
  if (resumePendant) {
    suspended.remove(pendantSuspension);
    if (state.connectedDevice == null) {
      effects.add(PolicyWrite(pendantSuspension!.wasPaused));
      effects.add(RunStage(ResumeSuspendedPendantStage(wasPaused: pendantSuspension.wasPaused)));
      return CaptureTransition(
        state.copyWith(
          phase: CapturePhase.idle,
          active: () => null,
          suspended: suspended,
          mutedBeforePhone: () => null,
          micInterrupted: false,
        ),
        effects,
      );
    }
    final seq = state.sessionSeq + 1;
    final key = 'pendant-$seq';
    final nextPhase = _pendantResumePhase(pendantSuspension!.mode, pendantSuspension.wasPaused);
    final nextActive = ActiveCaptureSession(
      source: CaptureSource.pendant,
      mode: pendantSuspension.mode,
      sessionKey: key,
      deviceId: pendantSuspension.deviceId,
      deviceType: pendantSuspension.deviceType,
    );
    effects.add(PolicyWrite(pendantSuspension.wasPaused));
    effects
      ..add(MintRecording(
        sessionKey: key,
        telemetrySource: pendantSuspension.mode == CaptureTransport.batch ? 'pendant_batch' : 'pendant_live',
      ))
      ..add(const RunStage(StartDeviceSessionStage(deviceRequested: true, promptLocation: false)));
    return CaptureTransition(
      state.copyWith(
        phase: nextPhase,
        active: () => nextActive,
        suspended: suspended,
        mutedBeforePhone: () => null,
        micInterrupted: false,
        sessionSeq: seq,
      ),
      effects,
    );
  }

  // A suspension with no live taker (no call holding it, no resume requested)
  // is dropped rather than stranded: the pendant's conversation already ended
  // when the phone took over.
  if (pendantSuspension != null) suspended.remove(pendantSuspension);

  effects.add(RunStage(StopPhonePolicyRestoreStage(
    mutedBefore: mutedBefore,
    pendantResumeFollows: pendantSuspension?.reason == SuspendReason.phone,
    userStop: event.userStop,
  )));

  return CaptureTransition(
    state.copyWith(
      phase: CapturePhase.idle,
      active: () => null,
      suspended: suspended,
      mutedBeforePhone: () => event.userStop ? null : state.mutedBeforePhone,
      micInterrupted: false,
    ),
    effects,
  );
}

CaptureTransition _reduceFinish(CaptureCoordinatorState state) {
  if (!state.phoneOwns) {
    return CaptureTransition(state, const [RunStage(ProcessConversationStage())]);
  }
  final wasBatch = state.phase == CapturePhase.phoneBatchLive || state.phase == CapturePhase.phoneBatchPaused;
  final suspended = List<SuspendedCapture>.of(state.suspended);
  final pendantSuspension = state.pendantSuspension;
  final mutedBefore = state.mutedBeforePhone;

  final effects = <CaptureEffect>[const PolicyWrite(true)];
  effects.add(RunStage(
      wasBatch ? const StopPhoneBatchStage(reason: 'user_stopped') : const StopPhoneLiveStage(reason: 'user_stopped')));

  if (pendantSuspension?.reason == SuspendReason.phone) {
    suspended.remove(pendantSuspension);
    if (!wasBatch) effects.add(const RunStage(ProcessConversationStage()));
    if (state.callActive) {
      // Same rule as a phone stop mid-call: the call keeps the channel, the
      // pendant's conversation already ended, so only its pre-handoff identity
      // survives to the call-end resume.
      suspended.add(SuspendedCapture(
        source: CaptureSource.pendant,
        reason: SuspendReason.call,
        wasPaused: pendantSuspension!.wasPaused,
        mode: pendantSuspension.mode,
        deviceId: pendantSuspension.deviceId ?? state.connectedDevice?.id,
        deviceType: pendantSuspension.deviceType ?? state.connectedDevice?.type,
      ));
      return CaptureTransition(
        state.copyWith(
          phase: CapturePhase.callActive,
          active: () => null,
          suspended: suspended,
          micInterrupted: false,
        ),
        effects,
      );
    }
    effects.add(PolicyWrite(pendantSuspension!.wasPaused));
    if (state.connectedDevice == null) {
      effects.add(RunStage(ResumeSuspendedPendantStage(wasPaused: pendantSuspension.wasPaused)));
      return CaptureTransition(
        state.copyWith(
          phase: CapturePhase.idle,
          active: () => null,
          suspended: suspended,
          mutedBeforePhone: () => null,
          micInterrupted: false,
        ),
        effects,
      );
    }
    final seq = state.sessionSeq + 1;
    final key = 'pendant-$seq';
    final nextPhase = _pendantResumePhase(pendantSuspension.mode, pendantSuspension.wasPaused);
    effects
      ..add(MintRecording(
        sessionKey: key,
        telemetrySource: pendantSuspension.mode == CaptureTransport.batch ? 'pendant_batch' : 'pendant_live',
      ))
      ..add(const RunStage(StartDeviceSessionStage(deviceRequested: true, promptLocation: false)));
    return CaptureTransition(
      state.copyWith(
        phase: nextPhase,
        active: () => ActiveCaptureSession(
          source: CaptureSource.pendant,
          mode: pendantSuspension.mode,
          sessionKey: key,
          deviceId: pendantSuspension.deviceId,
          deviceType: pendantSuspension.deviceType,
        ),
        suspended: suspended,
        mutedBeforePhone: () => null,
        micInterrupted: false,
        sessionSeq: seq,
      ),
      effects,
    );
  }

  if (!wasBatch) effects.add(const RunStage(ProcessConversationStage()));
  if (state.callActive) {
    return CaptureTransition(
      state.copyWith(
        phase: CapturePhase.callActive,
        active: () => null,
        suspended: suspended,
        micInterrupted: false,
      ),
      effects,
    );
  }
  effects.add(RunStage(StopPhonePolicyRestoreStage(
    mutedBefore: mutedBefore,
    pendantResumeFollows: false,
    userStop: true,
  )));
  return CaptureTransition(
    state.copyWith(
      phase: CapturePhase.idle,
      active: () => null,
      suspended: suspended,
      mutedBeforePhone: () => null,
      micInterrupted: false,
    ),
    effects,
  );
}

CaptureTransition _reducePause(CaptureCoordinatorState state, CaptureEnvironment env) {
  return switch (state.phase) {
    CapturePhase.phoneLive => CaptureTransition(
        state.copyWith(phase: CapturePhase.phonePaused),
        const [
          PolicyWrite(true),
          RunStage(FlushPhoneFramesStage()),
          NativeMicStop(),
          RunStage(RecordingMarkStage(RecordingState.pause)),
        ],
      ),
    CapturePhase.phoneBatchLive => CaptureTransition(
        state.copyWith(phase: CapturePhase.phoneBatchPaused),
        const [PolicyWrite(true)],
      ),
    CapturePhase.pendantLive => CaptureTransition(
        state.copyWith(phase: CapturePhase.pendantPaused),
        const [PolicyWrite(true), RunStage(PauseDeviceTailStage())],
      ),
    CapturePhase.pendantBatchLive => CaptureTransition(
        state.copyWith(phase: CapturePhase.pendantBatchPaused),
        const [PolicyWrite(true), RunStage(PauseDeviceTailStage())],
      ),
    // A suspended pendant only records wasPaused — pausing must never write
    // the shared policy under another owner or under a call.
    _ when state.pendantSuspension != null => CaptureTransition(
        state.copyWith(suspended: _withPendantWasPaused(state.suspended, true)),
        const [],
      ),
    _ when state.connectedDevice != null && !state.phoneOwns && !state.callActive => CaptureTransition(
        state,
        const [PolicyWrite(true), RunStage(PauseDeviceTailStage())],
      ),
    _ => CaptureTransition(state, const []),
  };
}

CaptureTransition _reduceResume(CaptureCoordinatorState state, CaptureEnvironment env) {
  return switch (state.phase) {
    CapturePhase.phonePaused => CaptureTransition(
        state.copyWith(phase: CapturePhase.phoneLive),
        const [
          PolicyWrite(false),
          // The socket may have closed during a long pause; reopen it for the
          // same recording (narrow phone-paused socket exception: the pause
          // keeps socket and recording id, it only stops audio).
          SocketOpen(codec: BleAudioCodec.pcm16, sampleRate: 16000, ensureOnly: true),
          NativeMicStart(PhoneMicSessionMode.live),
        ],
      ),
    CapturePhase.phoneBatchPaused => CaptureTransition(
        state.copyWith(phase: CapturePhase.phoneBatchLive),
        const [PolicyWrite(false)],
      ),
    CapturePhase.pendantPaused => CaptureTransition(
        state.copyWith(phase: CapturePhase.pendantLive),
        const [PolicyWrite(false), RunStage(ResumeDeviceTailStage())],
      ),
    CapturePhase.pendantBatchPaused => CaptureTransition(
        state.copyWith(phase: CapturePhase.pendantBatchLive),
        const [PolicyWrite(false), RunStage(ResumeDeviceTailStage())],
      ),
    _ when state.pendantSuspension != null => CaptureTransition(
        state.copyWith(suspended: _withPendantWasPaused(state.suspended, false)),
        const [],
      ),
    _ when state.connectedDevice != null && !state.phoneOwns && !state.callActive => CaptureTransition(
        state,
        const [PolicyWrite(false), RunStage(ResumeDeviceTailStage())],
      ),
    _ => CaptureTransition(state, const []),
  };
}

void _refreshPendantSuspensionDevice(List<SuspendedCapture> suspended, ConnectedDevice connected) {
  final index = suspended.lastIndexWhere((e) => e.source == CaptureSource.pendant);
  if (index < 0) return;
  final entry = suspended[index];
  suspended[index] = SuspendedCapture(
    source: entry.source,
    reason: entry.reason,
    wasPaused: entry.wasPaused,
    mode: entry.mode,
    sessionKey: entry.sessionKey,
    recordingId: entry.recordingId,
    deviceId: connected.id,
    deviceType: connected.type,
  );
}

List<SuspendedCapture> _withPendantWasPaused(List<SuspendedCapture> suspended, bool wasPaused) {
  final next = List<SuspendedCapture>.of(suspended);
  for (var i = next.length - 1; i >= 0; i--) {
    final entry = next[i];
    if (entry.source == CaptureSource.pendant) {
      next[i] = SuspendedCapture(
        source: entry.source,
        reason: entry.reason,
        wasPaused: wasPaused,
        mode: entry.mode,
        sessionKey: entry.sessionKey,
        recordingId: entry.recordingId,
        deviceId: entry.deviceId,
        deviceType: entry.deviceType,
      );
      break;
    }
  }
  return next;
}

CaptureTransition _reduceOfflineMuteToggle(CaptureCoordinatorState state, CaptureEnvironment env) {
  if (env.paused) {
    // Unmuting routes through the phase-correct resume: a paused owner really
    // resumes, a suspended pendant only records its resume intent, and the
    // shared policy is never flipped under another owner or a call.
    if (state.connectedDevice != null || state.phoneOwns || state.pendantSuspension != null) {
      return _reduceResume(state, env);
    }
    if (state.callActive) return CaptureTransition(state, const []);
    return CaptureTransition(state, const [PolicyWrite(false)]);
  }
  return _reduceDevicePause(state, env);
}

CaptureTransition _reduceDeviceStart(
    CaptureCoordinatorState state, DeviceStartRequested event, CaptureEnvironment env) {
  final effects = <CaptureEffect>[];
  final device = event.device;
  final connected = device != null ? ConnectedDevice(id: device.id, type: device.type) : state.connectedDevice;
  if (device != null) {
    effects.add(RunStage(UpdateRecordingDeviceStage(device)));
  }
  final suspended = List<SuspendedCapture>.of(state.suspended);

  if (state.phoneOwns || state.callActive) {
    // The phone or a call has the capture: remember the pendant and start it
    // when that ends. Its transcript and session stay intact.
    if (connected != null) {
      if (state.pendantSuspension == null) {
        suspended.add(SuspendedCapture(
          source: CaptureSource.pendant,
          reason: state.phoneOwns ? SuspendReason.phone : SuspendReason.call,
          wasPaused: state.phoneOwns ? (state.mutedBeforePhone ?? false) : env.paused,
          mode: env.batchModeEnabled ? CaptureTransport.batch : CaptureTransport.live,
          deviceId: connected.id,
          deviceType: connected.type,
        ));
      } else {
        // No duplicate debt: a repeated start only refreshes the resume target
        // to the device the user actually asked for.
        _refreshPendantSuspensionDevice(suspended, connected);
      }
    }
    return CaptureTransition(
      state.copyWith(
        suspended: suspended,
        connectedDevice: () => connected,
      ),
      effects,
    );
  }

  if (connected == null) {
    // Check-only call with nothing connected: still runs the reset tail.
    return CaptureTransition(
        state, effects..add(const RunStage(StartDeviceSessionStage(deviceRequested: false, promptLocation: false))));
  }

  if (state.pendantSuspension != null) {
    // No owner holds the channel (phone and call were both excluded above), so
    // the debt has no taker: a preserved call session resumes as-is, anything
    // else is dropped and the start below opens a fresh session.
    final index = suspended.lastIndexWhere((e) => e.source == CaptureSource.pendant);
    final entry = suspended[index];
    suspended.removeAt(index);
    // A call suspension preserves its conversation; a phone suspension's
    // conversation already ended at takeover, so it starts fresh.
    if (entry.reason == SuspendReason.call && entry.sessionKey != null) {
      if (entry.wasPaused != env.policyMuted) {
        effects.add(PolicyWrite(entry.wasPaused));
      }
      effects.add(RunStage(ResumeSuspendedPendantStage(wasPaused: entry.wasPaused)));
      return CaptureTransition(
        state.copyWith(
          phase: _pendantResumePhase(entry.mode, entry.wasPaused),
          active: () => ActiveCaptureSession(
            source: CaptureSource.pendant,
            mode: entry.mode,
            sessionKey: entry.sessionKey!,
            recordingId: entry.recordingId,
            deviceId: connected.id,
            deviceType: connected.type,
          ),
          suspended: suspended,
          connectedDevice: () => connected,
        ),
        effects,
      );
    }
  }

  final seq = state.sessionSeq + 1;
  final key = 'pendant-$seq';
  final mode = env.batchModeEnabled ? CaptureTransport.batch : CaptureTransport.live;
  final phase = env.paused
      ? (mode == CaptureTransport.batch ? CapturePhase.pendantBatchPaused : CapturePhase.pendantPaused)
      : (mode == CaptureTransport.batch ? CapturePhase.pendantBatchLive : CapturePhase.pendantLive);

  effects.add(MintRecording(
    sessionKey: key,
    telemetrySource: mode == CaptureTransport.batch ? 'pendant_batch' : 'pendant_live',
  ));
  effects.add(RunStage(StartDeviceSessionStage(deviceRequested: true, promptLocation: device != null)));

  return CaptureTransition(
    state.copyWith(
      phase: phase,
      active: () => ActiveCaptureSession(
        source: CaptureSource.pendant,
        mode: mode,
        sessionKey: key,
        deviceId: connected.id,
        deviceType: connected.type,
      ),
      suspended: suspended,
      connectedDevice: () => connected,
      sessionSeq: seq,
      lastFailure: () => null,
    ),
    effects,
  );
}

CaptureTransition _reduceDeviceStop(CaptureCoordinatorState state, DeviceStopRequested event) {
  if (!state.pendantOwns) {
    // Another source owns capture: the stop only updates pendant identity
    // (cleanDevice clears _recordingDevice) and never touches the owner's
    // socket, WAL, recording state, or the suspension stack.
    return CaptureTransition(
      state.copyWith(connectedDevice: () => event.cleanDevice ? null : state.connectedDevice),
      [if (event.cleanDevice) const RunStage(UpdateRecordingDeviceStage(null))],
    );
  }
  return CaptureTransition(
    state.copyWith(
      phase: CapturePhase.idle,
      active: () => null,
      connectedDevice: () => event.cleanDevice ? null : state.connectedDevice,
    ),
    [
      RunStage(StopDeviceSessionStage(cleanDevice: event.cleanDevice)),
      const SocketClose('stop stream device recording'),
      RunStage(DeviceStopTelemetryStage(cleanDevice: event.cleanDevice)),
    ],
  );
}

CaptureTransition _reduceDeviceUpdated(CaptureCoordinatorState state, DeviceUpdated event) {
  final device = event.device;
  final connected = device == null ? null : ConnectedDevice(id: device.id, type: device.type);
  final suspended = List<SuspendedCapture>.of(state.suspended);
  var phase = state.phase;
  var active = state.active;
  final effects = <CaptureEffect>[];

  if (connected == null) {
    // A call's suspension outlives a BLE drop; a phone's does not.
    final index = suspended.lastIndexWhere((e) => e.source == CaptureSource.pendant && e.reason == SuspendReason.phone);
    if (index >= 0) suspended.removeAt(index);
    if (state.pendantOwns) {
      phase = CapturePhase.idle;
      active = null;
      // No per-source native gate exists: a batch pendant's writer is only
      // deniable through the shared policy mute (honest limitation — the gate
      // call below is a no-op until a native gate lands).
      if (state.phase == CapturePhase.pendantBatchLive || state.phase == CapturePhase.pendantBatchPaused) {
        effects.add(const PolicyWrite(true));
      }
      // The full pendant teardown (BLE streams, WAL finalize, recording state,
      // device identity, telemetry) runs in the stage; the socket close stays
      // an ordered effect so no stage duplicates it.
      effects
        ..add(const NativeWriterGate(source: CaptureSource.pendant, admitted: false))
        ..add(const RunStage(StopDeviceSessionStage(cleanDevice: true)))
        ..add(const SocketClose('device disconnected'))
        ..add(const RunStage(DeviceStopTelemetryStage(cleanDevice: true)));
    } else {
      effects.add(RunStage(UpdateRecordingDeviceStage(device)));
    }
  } else {
    if (active != null && active.source == CaptureSource.pendant) {
      active = active.copyWith(deviceId: connected.id, deviceType: connected.type);
    }
    _refreshPendantSuspensionDevice(suspended, connected);
    effects.add(RunStage(UpdateRecordingDeviceStage(device)));
  }

  return CaptureTransition(
    state.copyWith(
      phase: phase,
      active: () => active,
      suspended: suspended,
      connectedDevice: () => connected,
    ),
    effects,
  );
}

CaptureTransition _reduceDevicePause(CaptureCoordinatorState state, CaptureEnvironment env) {
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
    return CaptureTransition(
      state.copyWith(phase: nextPhase),
      const [PolicyWrite(true), RunStage(PauseDeviceTailStage())],
    );
  }
  // An unowned pendant control only records suspended intent; the legacy
  // idle mute persists admission without opening any capture source.
  if (state.pendantSuspension != null) {
    return CaptureTransition(
      state.copyWith(suspended: _withPendantWasPaused(state.suspended, true)),
      const [],
    );
  }
  if (state.phase == CapturePhase.idle && !state.callActive) {
    return CaptureTransition(state, const [PolicyWrite(true), RunStage(PauseDeviceTailStage())]);
  }
  return CaptureTransition(state, const []);
}

CaptureTransition _reduceDeviceResume(CaptureCoordinatorState state, CaptureEnvironment env) {
  if (state.phase == CapturePhase.phonePaused || state.phase == CapturePhase.phoneBatchPaused) {
    return _reduceResume(state, env);
  }
  if (state.phoneOwns) return CaptureTransition(state, const []);
  final nextPhase = switch (state.phase) {
    CapturePhase.pendantPaused => CapturePhase.pendantLive,
    CapturePhase.pendantBatchPaused => CapturePhase.pendantBatchLive,
    _ => state.phase,
  };
  if (nextPhase != state.phase) {
    return CaptureTransition(
      state.copyWith(phase: nextPhase),
      const [PolicyWrite(false), RunStage(ResumeDeviceTailStage())],
    );
  }
  if (state.pendantSuspension != null) {
    return CaptureTransition(
      state.copyWith(suspended: _withPendantWasPaused(state.suspended, false)),
      const [],
    );
  }
  return CaptureTransition(state, const []);
}

CaptureTransition _reduceCall(CaptureCoordinatorState state, CaptureEnvironment env) {
  if (env.callActive) {
    if (state.callActive) {
      // A repeated call-start or reconnect while the call already holds adds
      // no suspension debt.
      return CaptureTransition(state, const []);
    }
    if (!state.pendantOwns) {
      return CaptureTransition(state.copyWith(callActive: true), const []);
    }
    final wasPaused = state.phase == CapturePhase.pendantPaused || state.phase == CapturePhase.pendantBatchPaused;
    final suspended = List<SuspendedCapture>.of(state.suspended)
      ..add(SuspendedCapture(
        source: CaptureSource.pendant,
        reason: SuspendReason.call,
        wasPaused: wasPaused,
        mode: state.active?.mode ?? CaptureTransport.live,
        sessionKey: state.active?.sessionKey,
        recordingId: state.active?.recordingId,
        deviceId: state.active?.deviceId ?? state.connectedDevice?.id,
        deviceType: state.active?.deviceType ?? state.connectedDevice?.type,
      ));
    final effects = <CaptureEffect>[
      if (state.active?.mode == CaptureTransport.batch) const PolicyWrite(true),
      const NativeWriterGate(source: CaptureSource.pendant, admitted: false),
      const BleStreamStop(disableNativeBackground: true),
    ];
    effects.add(RunStage(SuspendPendantStage(reason: SuspendReason.call, wasPaused: wasPaused)));
    return CaptureTransition(
      state.copyWith(
        phase: CapturePhase.callActive,
        active: () => null,
        suspended: suspended,
        callActive: true,
      ),
      effects,
    );
  }

  final suspended = List<SuspendedCapture>.of(state.suspended);
  final mutedBeforePhone = state.mutedBeforePhone;
  final index = suspended.lastIndexWhere((e) => e.source == CaptureSource.pendant && e.reason == SuspendReason.call);
  // A call that ends while the phone still owns capture releases nothing —
  // any suspension stays until the phone itself stops.
  if (index < 0 || state.phoneOwns) {
    return CaptureTransition(
      state.copyWith(
        phase: state.phase == CapturePhase.callActive ? CapturePhase.idle : state.phase,
        callActive: false,
        // The phone's deferred policy restore is still owned by its stop.
        mutedBeforePhone: () => state.phoneOwns ? mutedBeforePhone : null,
      ),
      [
        if (!state.phoneOwns && mutedBeforePhone != null) PolicyWrite(mutedBeforePhone),
      ],
    );
  }
  final entry = suspended.removeAt(index);
  // A phone suspension only lives while the phone owns capture; clear any
  // straggler so an idle result never carries debt with no taker.
  suspended.removeWhere((e) => e.source == CaptureSource.pendant && e.reason == SuspendReason.phone);
  final effects = <CaptureEffect>[];
  if (entry.wasPaused != env.policyMuted) {
    effects.add(PolicyWrite(entry.wasPaused));
  }

  if (state.connectedDevice == null) {
    effects.add(RunStage(ResumeSuspendedPendantStage(wasPaused: entry.wasPaused)));
    return CaptureTransition(
      state.copyWith(
        phase: CapturePhase.idle,
        active: () => null,
        suspended: suspended,
        callActive: false,
        mutedBeforePhone: () => null,
      ),
      effects,
    );
  }

  if (entry.sessionKey == null) {
    // The phone ended this pendant's conversation when it took over during the
    // call, so the resume starts a fresh session with a newly minted id.
    final seq = state.sessionSeq + 1;
    final key = 'pendant-$seq';
    effects
      ..add(MintRecording(
        sessionKey: key,
        telemetrySource: entry.mode == CaptureTransport.batch ? 'pendant_batch' : 'pendant_live',
      ))
      ..add(const RunStage(StartDeviceSessionStage(deviceRequested: true, promptLocation: false)));
    return CaptureTransition(
      state.copyWith(
        phase: _pendantResumePhase(entry.mode, entry.wasPaused),
        active: () => ActiveCaptureSession(
          source: CaptureSource.pendant,
          mode: entry.mode,
          sessionKey: key,
          deviceId: entry.deviceId ?? state.connectedDevice?.id,
          deviceType: entry.deviceType ?? state.connectedDevice?.type,
        ),
        suspended: suspended,
        callActive: false,
        mutedBeforePhone: () => null,
        sessionSeq: seq,
      ),
      effects,
    );
  }

  effects.add(RunStage(ResumeSuspendedPendantStage(wasPaused: entry.wasPaused)));
  return CaptureTransition(
    state.copyWith(
      phase: _pendantResumePhase(entry.mode, entry.wasPaused),
      active: () => ActiveCaptureSession(
        source: CaptureSource.pendant,
        mode: entry.mode,
        sessionKey: entry.sessionKey!,
        recordingId: entry.recordingId,
        deviceId: entry.deviceId ?? state.connectedDevice?.id,
        deviceType: entry.deviceType ?? state.connectedDevice?.type,
      ),
      suspended: suspended,
      callActive: false,
      mutedBeforePhone: () => null,
    ),
    effects,
  );
}

CaptureTransition _reduceMicInterruption(CaptureCoordinatorState state, MicInterruptionChanged event) {
  if (!state.phoneOwns) return CaptureTransition(state, const []);
  var phase = state.phase;
  if (event.began && (phase == CapturePhase.phoneLive || phase == CapturePhase.phoneBatchLive)) {
    phase = CapturePhase.audioInterrupted;
  } else if (!event.began && phase == CapturePhase.audioInterrupted) {
    phase = state.active?.mode == CaptureTransport.batch ? CapturePhase.phoneBatchLive : CapturePhase.phoneLive;
  }
  return CaptureTransition(
    state.copyWith(phase: phase, micInterrupted: event.began),
    [RunStage(MicInterruptionStage(began: event.began))],
  );
}

CaptureTransition _reduceMicStalled(CaptureCoordinatorState state) {
  return switch (state.phase) {
    CapturePhase.phoneLive when !state.micInterrupted =>
      CaptureTransition(state, const [RunStage(RestartLiveMicStage())]),
    CapturePhase.phoneBatchLive when !state.micInterrupted =>
      CaptureTransition(state, const [RunStage(RestartBatchMicStage())]),
    _ => CaptureTransition(state, const []),
  };
}

CaptureTransition _reduceAppForegrounded(CaptureCoordinatorState state) {
  if (!state.phoneOwns || state.micInterrupted) return CaptureTransition(state, const []);
  return CaptureTransition(state, const [RunStage(ProbeStallStage())]);
}

CaptureTransition _reduceKeepAlive(CaptureCoordinatorState state, KeepAliveTick event, CaptureEnvironment env) {
  if (event.testingProbe) {
    if (env.deviceRecording && state.connectedDevice != null && !env.paused) {
      return CaptureTransition(state, const [RunStage(ReconnectDeviceStage())]);
    }
    if (env.micCapturing) return CaptureTransition(state, const [RunStage(ReconnectPhoneStage())]);
  }
  if (!env.deviceServiceReady || env.transcriptReady || !env.signedIn()) {
    return CaptureTransition(state, const []);
  }
  if (state.phase == CapturePhase.pendantLive && env.deviceRecording && !env.paused) {
    return CaptureTransition(state, const [RunStage(ReconnectDeviceStage())]);
  }
  if (env.micCapturing && (state.phoneOwns || env.systemAudioRecording)) {
    return CaptureTransition(state, const [RunStage(ReconnectPhoneStage())]);
  }
  return CaptureTransition(state, const []);
}

CaptureTransition _reduceBatchMode(CaptureCoordinatorState state, BatchModeSetRequested event, CaptureEnvironment env) {
  if (state.connectedDevice != null && event.enabled && !env.deviceSupportsTranscribeLater) {
    // Refused: no batch capture path for this device.
    return CaptureTransition(state, [RunStage(BatchModeStage(enabled: event.enabled))]);
  }
  var phase = state.phase;
  var active = state.active;
  var seq = state.sessionSeq;
  final effects = <CaptureEffect>[];

  CapturePhase pendantPhaseFor(bool paused) => event.enabled
      ? (paused ? CapturePhase.pendantBatchPaused : CapturePhase.pendantBatchLive)
      : (paused ? CapturePhase.pendantPaused : CapturePhase.pendantLive);

  switch (state.phase) {
    case CapturePhase.pendantLive:
    case CapturePhase.pendantPaused:
    case CapturePhase.pendantBatchLive:
    case CapturePhase.pendantBatchPaused:
      phase =
          pendantPhaseFor(state.phase == CapturePhase.pendantPaused || state.phase == CapturePhase.pendantBatchPaused);
      if (active != null) {
        active = ActiveCaptureSession(
          source: active.source,
          mode: event.enabled ? CaptureTransport.batch : CaptureTransport.live,
          sessionKey: active.sessionKey,
          recordingId: active.recordingId,
          deviceId: active.deviceId,
          deviceType: active.deviceType,
        );
      }
    case CapturePhase.phoneLive:
    case CapturePhase.phoneBatchLive:
      // A live phone session rolls into the new mode; a paused one keeps its
      // session and applies the mode to the next recording.
      seq += 1;
      phase = event.enabled ? CapturePhase.phoneBatchLive : CapturePhase.phoneLive;
      active = ActiveCaptureSession(
        source: CaptureSource.phone,
        mode: event.enabled ? CaptureTransport.batch : CaptureTransport.live,
        sessionKey: 'phone-$seq',
      );
      effects.add(MintRecording(
        sessionKey: 'phone-$seq',
        telemetrySource: event.enabled ? 'phone_mic_batch' : 'phone_mic_live',
      ));
    default:
      break;
  }
  effects.add(RunStage(BatchModeStage(
    enabled: event.enabled,
    rolledPhoneMode: switch (state.phase) {
      CapturePhase.phoneLive => CaptureTransport.live,
      CapturePhase.phoneBatchLive => CaptureTransport.batch,
      _ => null,
    },
  )));
  return CaptureTransition(
    state.copyWith(phase: phase, active: () => active, sessionSeq: seq),
    effects,
  );
}

CaptureTransition _reduceOnboardingBatch(CaptureCoordinatorState state, OnboardingBatchChanged event) {
  // Suspending flips batchMode off (pendant -> live), restoring flips it on.
  var phase = state.phase;
  var active = state.active;
  final toBatch = !event.suspended;
  switch (state.phase) {
    case CapturePhase.pendantLive:
    case CapturePhase.pendantBatchLive:
      phase = toBatch ? CapturePhase.pendantBatchLive : CapturePhase.pendantLive;
      if (active != null) {
        active = ActiveCaptureSession(
          source: active.source,
          mode: toBatch ? CaptureTransport.batch : CaptureTransport.live,
          sessionKey: active.sessionKey,
          recordingId: active.recordingId,
          deviceId: active.deviceId,
          deviceType: active.deviceType,
        );
      }
    case CapturePhase.pendantPaused:
    case CapturePhase.pendantBatchPaused:
      phase = toBatch ? CapturePhase.pendantBatchPaused : CapturePhase.pendantPaused;
      if (active != null) {
        active = ActiveCaptureSession(
          source: active.source,
          mode: toBatch ? CaptureTransport.batch : CaptureTransport.live,
          sessionKey: active.sessionKey,
          recordingId: active.recordingId,
          deviceId: active.deviceId,
          deviceType: active.deviceType,
        );
      }
    default:
      break;
  }
  return CaptureTransition(
    state.copyWith(phase: phase, active: () => active),
    [RunStage(OnboardingBatchStage(suspended: event.suspended))],
  );
}

CaptureTransition _reducePhoneBatchStart(CaptureCoordinatorState state, PhoneBatchStartRequested event) {
  // Repeated start while the phone owns is a no-op; any pendant-owned or
  // call-held channel is refused — no suspension/teardown path exists for a
  // direct batch start, and a native writer must never overlap another owner.
  if (state.phoneOwns || state.pendantOwns || state.callActive) {
    return CaptureTransition(state, const []);
  }
  final seq = state.sessionSeq + 1;
  final key = 'phone-$seq';
  return CaptureTransition(
    state.copyWith(
      phase: CapturePhase.phoneBatchLive,
      active: () => ActiveCaptureSession(source: CaptureSource.phone, mode: CaptureTransport.batch, sessionKey: key),
      micInterrupted: false,
      sessionSeq: seq,
    ),
    [
      MintRecording(
        sessionKey: key,
        telemetrySource: event.auto ? 'phone_mic_batch_auto' : 'phone_mic_batch',
      ),
      RunStage(StartPhoneBatchStage(auto: event.auto)),
    ],
  );
}

CaptureTransition _reduceLaunchRecovery(CaptureCoordinatorState state, LaunchRecovery event, CaptureEnvironment env) {
  if (!event.markerPending) return CaptureTransition(state, const []);
  final effects = <CaptureEffect>[const RunStage(ClearPhoneRestoreMarkerStage())];
  if (!state.phoneOwns && env.paused != event.mutedBefore) {
    effects.add(PolicyWrite(event.mutedBefore));
  }
  return CaptureTransition(state, effects);
}

class _MintedRecordingId {
  const _MintedRecordingId(this.sessionKey, this.recordingId);
  final String sessionKey;
  final String recordingId;
}
