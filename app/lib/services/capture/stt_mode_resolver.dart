import 'package:omi/models/stt_provider.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/free_tier_on_device_stt_flag.dart';
import 'package:omi/services/capture/on_device_stt_preparer.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/transcription_service.dart';

enum SttResolvedPath {
  /// Today's Omi managed socket (`customSttConfig == null`).
  managed,

  /// Honor the user's persisted Custom STT config.
  honorCustom,

  /// Synthesized on-device config (`freemium:on-device`).
  onDevice,

  /// No transcription socket. Never a billed fallback.
  blocked,
}

class SttModeDecision {
  final SttResolvedPath path;
  final CustomSttConfig? customSttConfig;
  final String reason;
  final bool allowanceOnDevice;

  const SttModeDecision({
    required this.path,
    required this.reason,
    this.customSttConfig,
    this.allowanceOnDevice = false,
  });

  bool get opensManagedOmiSocket => path == SttResolvedPath.managed;

  bool get blockSocket => path == SttResolvedPath.blocked;

  String get socketIdentity {
    if (blockSocket) return 'blocked';
    return customSttConfig?.sttConfigId ?? 'omi:default';
  }
}

/// Plan-authoritative STT mode. Reads S16's snapshot; does not re-derive it.
///
/// Order (flag on): persisted Custom STT → allowance `blocked` → allowance `managed` →
/// allowance `on_device` (ready ⇒ synthesize on-device). Every case where the phone cannot
/// transcribe yet (no snapshot, a transient server reason, model not ready, unsupported codec,
/// no config) keeps today's Omi socket: the server still enforces the cap there, so the user is
/// never worse off than with the flag off. A not-ready phone is asked to prepare its model.
class SttModeResolver {
  static const freemiumOnDeviceId = 'freemium:on-device';

  /// Reasons the decision routes managed because the phone is not ready yet.
  static const reasonNotReady = 'on_device_not_ready';
  static const reasonUnsupportedCodec = 'unsupported_codec_on_device';
  static const reasonConfigUnavailable = 'on_device_config_unavailable';
  static const reasonAllowanceUnknown = 'allowance_unknown';

  /// Server reasons that mean "the lookup could not be trusted", not "the minutes are spent".
  /// Mirrors backend TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS.
  static const transientAllowanceReasons = {'allowance_unavailable', 'usage_invalid'};

  static SttModeResolver instance = SttModeResolver();

  final bool Function() flagReader;
  final Future<bool> Function() killSwitchReader;
  final void Function({String? language}) prepareOnDevice;
  final TranscriptionAllowanceSnapshot? Function() allowanceReader;
  final Future<FreemiumReadiness> Function({String? language}) readinessReader;
  final CustomSttConfig? Function() onDeviceConfigBuilder;

  SttModeResolver({
    bool Function()? flagReader,
    TranscriptionAllowanceSnapshot? Function()? allowanceReader,
    Future<FreemiumReadiness> Function({String? language})? readinessReader,
    CustomSttConfig? Function()? onDeviceConfigBuilder,
    Future<bool> Function()? killSwitchReader,
    void Function({String? language})? prepareOnDevice,
  })  : flagReader = flagReader ?? _defaultFlag,
        killSwitchReader = killSwitchReader ?? FreeTierOnDeviceSttFlag.killed,
        prepareOnDevice = prepareOnDevice ?? OnDeviceSttPreparer.prepare,
        allowanceReader = allowanceReader ?? _defaultAllowance,
        readinessReader = readinessReader ?? _defaultReadiness,
        onDeviceConfigBuilder = onDeviceConfigBuilder ?? _defaultOnDeviceConfig;

  @visibleForTesting
  static void debugResetInstance() {
    instance = SttModeResolver();
  }

  static bool _defaultFlag() => FreeTierOnDeviceSttFlag.isEnabled();

  static TranscriptionAllowanceSnapshot? _defaultAllowance() => TranscriptionAllowanceCache.current;

  static Future<FreemiumReadiness> _defaultReadiness({String? language}) =>
      FreemiumTranscriptionService().checkReadiness(language: language);

  static CustomSttConfig? _defaultOnDeviceConfig() {
    final config = FreemiumTranscriptionService().getFreemiumConfig();
    if (config == null) return null;
    return config.copyWith(identity: freemiumOnDeviceId, sendRawAudioToOmi: false);
  }

  Future<SttModeDecision> decide({required CustomSttConfig persistedCustomStt, required BleAudioCodec codec}) async {
    FreemiumReadiness readiness = FreemiumReadiness.ready;
    final flag = flagReader() && !persistedCustomStt.isEnabled && !await killSwitchReader();
    final allowance = allowanceReader();
    if ((persistedCustomStt.provider == SttProvider.onDeviceWhisper &&
            !kIsWeb &&
            defaultTargetPlatform == TargetPlatform.iOS) ||
        (flag && !persistedCustomStt.isEnabled && _needsOnDeviceReadiness(allowance))) {
      readiness = await readinessReader(
          language: persistedCustomStt.isEnabled && persistedCustomStt.provider == SttProvider.onDeviceWhisper
              ? persistedCustomStt.language
              : null);
    }
    final decision = resolve(
      flagEnabled: flag,
      persistedCustomStt: persistedCustomStt,
      allowance: allowance,
      readiness: readiness,
      codec: codec,
    );
    if (decision.reason == reasonNotReady && !persistedCustomStt.isEnabled) {
      // Fire and forget: the next socket picks the model up once it is ready.
      prepareOnDevice();
    }
    return decision;
  }

  /// True when the snapshot asks this phone to transcribe (on_device, or an unknown mode).
  static bool wantsOnDevice(TranscriptionAllowanceSnapshot? allowance) {
    if (allowance == null || allowance.isManaged || allowance.isBlocked) return false;
    return !(allowance.isOnDevice && transientAllowanceReasons.contains(allowance.reason));
  }

  bool _needsOnDeviceReadiness(TranscriptionAllowanceSnapshot? allowance) => wantsOnDevice(allowance);

  SttModeDecision resolve({
    required bool flagEnabled,
    required CustomSttConfig persistedCustomStt,
    required TranscriptionAllowanceSnapshot? allowance,
    required FreemiumReadiness readiness,
    required BleAudioCodec codec,
  }) {
    if (persistedCustomStt.isEnabled) {
      if (persistedCustomStt.provider == SttProvider.onDeviceWhisper && readiness != FreemiumReadiness.ready) {
        return const SttModeDecision(
            path: SttResolvedPath.blocked, reason: 'on_device_not_ready', allowanceOnDevice: true);
      }
      return SttModeDecision(
        path: SttResolvedPath.honorCustom,
        customSttConfig: persistedCustomStt,
        reason: 'explicit_custom_stt',
      );
    }

    if (!flagEnabled) {
      return const SttModeDecision(path: SttResolvedPath.managed, reason: 'flag_off');
    }

    if (allowance == null) {
      // No snapshot yet (fresh install, signed-out cache): today's socket; the server enforces the cap.
      return const SttModeDecision(path: SttResolvedPath.managed, reason: reasonAllowanceUnknown);
    }

    if (allowance.isBlocked) {
      return SttModeDecision(path: SttResolvedPath.blocked, reason: allowance.reason, allowanceOnDevice: false);
    }

    if (!wantsOnDevice(allowance)) {
      // managed, or on_device for a transient lookup failure (not spent minutes).
      return SttModeDecision(path: SttResolvedPath.managed, reason: allowance.reason);
    }

    // on_device, or any unknown mode: the phone transcribes when it can.
    final onDeviceReason = allowance.isOnDevice ? allowance.reason : 'allowance_unrecognized';
    if (readiness != FreemiumReadiness.ready) {
      return const SttModeDecision(path: SttResolvedPath.managed, reason: reasonNotReady);
    }

    if (TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(codec, null, allowanceOnDevice: true)) {
      return const SttModeDecision(path: SttResolvedPath.managed, reason: reasonUnsupportedCodec);
    }

    final synthesized = onDeviceConfigBuilder();
    if (synthesized == null) {
      return const SttModeDecision(path: SttResolvedPath.managed, reason: reasonConfigUnavailable);
    }

    return SttModeDecision(
      path: SttResolvedPath.onDevice,
      customSttConfig: synthesized.copyWith(identity: freemiumOnDeviceId),
      reason: onDeviceReason,
      allowanceOnDevice: true,
    );
  }
}

PurePollingSocket? customSttPollingSocket(Object? socket) {
  final primary = socket is CompositeTranscriptionSocket ? socket.primarySocket : socket;
  return primary is PurePollingSocket ? primary : null;
}

/// When custom STT is configured, its polling socket keeps buffering audio
/// locally and retrying instead of tearing the transcription socket down on
/// every failure (see PurePollingSocket). Surface that local state so the
/// recording UI can show "offline, buffering" instead of silently showing
/// "Listening" while nothing is actually being transcribed.
Duration? customSttBufferingFor(Object? socket, [DateTime? now]) {
  final since = customSttPollingSocket(socket)?.bufferingSince;
  return since == null ? null : (now ?? DateTime.now()).difference(since);
}
