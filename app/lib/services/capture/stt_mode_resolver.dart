import 'package:flutter/foundation.dart';

import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/free_tier_on_device_stt_flag.dart';
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
/// Order (flag on): persisted Custom STT → allowance `managed` → allowance
/// `on_device` (ready ⇒ synthesize, else block) → allowance `blocked` →
/// missing snapshot fails closed to on-device (no billed socket).
class SttModeResolver {
  static const freemiumOnDeviceId = 'freemium:on-device';

  static SttModeResolver instance = SttModeResolver();

  final bool Function() flagReader;
  final TranscriptionAllowanceSnapshot? Function() allowanceReader;
  final Future<FreemiumReadiness> Function() readinessReader;
  final CustomSttConfig? Function() onDeviceConfigBuilder;

  SttModeResolver({
    bool Function()? flagReader,
    TranscriptionAllowanceSnapshot? Function()? allowanceReader,
    Future<FreemiumReadiness> Function()? readinessReader,
    CustomSttConfig? Function()? onDeviceConfigBuilder,
  })  : flagReader = flagReader ?? _defaultFlag,
        allowanceReader = allowanceReader ?? _defaultAllowance,
        readinessReader = readinessReader ?? _defaultReadiness,
        onDeviceConfigBuilder = onDeviceConfigBuilder ?? _defaultOnDeviceConfig;

  @visibleForTesting
  static void debugResetInstance() {
    instance = SttModeResolver();
  }

  static bool _defaultFlag() => FreeTierOnDeviceSttFlag.isEnabled();

  static TranscriptionAllowanceSnapshot? _defaultAllowance() => TranscriptionAllowanceCache.current;

  static Future<FreemiumReadiness> _defaultReadiness() => FreemiumTranscriptionService().checkReadiness();

  static CustomSttConfig? _defaultOnDeviceConfig() {
    final config = FreemiumTranscriptionService().getFreemiumConfig();
    if (config == null) return null;
    return config.copyWith(identity: freemiumOnDeviceId, sendRawAudioToOmi: false);
  }

  Future<SttModeDecision> decide({
    required CustomSttConfig persistedCustomStt,
    required BleAudioCodec codec,
  }) async {
    FreemiumReadiness readiness = FreemiumReadiness.ready;
    final flag = flagReader();
    final allowance = allowanceReader();
    if (flag && !persistedCustomStt.isEnabled && _needsOnDeviceReadiness(allowance)) {
      readiness = await readinessReader();
    }
    return resolve(
      flagEnabled: flag,
      persistedCustomStt: persistedCustomStt,
      allowance: allowance,
      readiness: readiness,
      codec: codec,
    );
  }

  bool _needsOnDeviceReadiness(TranscriptionAllowanceSnapshot? allowance) {
    if (allowance == null) return true;
    return allowance.isOnDevice;
  }

  SttModeDecision resolve({
    required bool flagEnabled,
    required CustomSttConfig persistedCustomStt,
    required TranscriptionAllowanceSnapshot? allowance,
    required FreemiumReadiness readiness,
    required BleAudioCodec codec,
  }) {
    if (persistedCustomStt.isEnabled) {
      return SttModeDecision(
        path: SttResolvedPath.honorCustom,
        customSttConfig: persistedCustomStt,
        reason: 'explicit_custom_stt',
      );
    }

    if (!flagEnabled) {
      return const SttModeDecision(path: SttResolvedPath.managed, reason: 'flag_off');
    }

    final effective = allowance ??
        const TranscriptionAllowanceSnapshot(
          mode: TranscriptionAllowanceSnapshot.modeOnDevice,
          reason: 'allowance_unavailable',
        );

    if (effective.isBlocked) {
      return SttModeDecision(path: SttResolvedPath.blocked, reason: effective.reason, allowanceOnDevice: false);
    }

    if (effective.isManaged) {
      return SttModeDecision(path: SttResolvedPath.managed, reason: effective.reason);
    }

    // on_device, or any unknown mode — fail closed, never a billed socket.
    final onDeviceReason = effective.isOnDevice ? effective.reason : 'allowance_unrecognized';
    if (readiness != FreemiumReadiness.ready) {
      return const SttModeDecision(
        path: SttResolvedPath.blocked,
        reason: 'on_device_not_ready',
        allowanceOnDevice: true,
      );
    }

    if (TranscriptSocketServiceFactory.shouldBlockUnsupportedCodecFallback(
      codec,
      null,
      allowanceOnDevice: true,
    )) {
      return const SttModeDecision(
        path: SttResolvedPath.blocked,
        reason: 'unsupported_codec_on_device',
        allowanceOnDevice: true,
      );
    }

    final synthesized = onDeviceConfigBuilder();
    if (synthesized == null) {
      return const SttModeDecision(
        path: SttResolvedPath.blocked,
        reason: 'on_device_config_unavailable',
        allowanceOnDevice: true,
      );
    }

    return SttModeDecision(
      path: SttResolvedPath.onDevice,
      customSttConfig: synthesized.copyWith(identity: freemiumOnDeviceId),
      reason: onDeviceReason,
      allowanceOnDevice: true,
    );
  }
}
