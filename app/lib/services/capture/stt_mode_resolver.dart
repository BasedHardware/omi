import 'package:omi/models/stt_provider.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/free_tier_on_device_stt_flag.dart';
import 'package:omi/services/capture/on_device_stt_preparer.dart';
import 'package:omi/services/capture/phone_transcription_choice.dart';
import 'package:omi/services/capture/transcription_allowance_cache.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/backend/preferences.dart';
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
///
/// The first on-device decision at the cap is persisted as the free plan's phone choice
/// ([PhoneTranscriptionChoice]); from then on the persisted config is honored like any Custom STT
/// (blocked, never billed, when the phone is not ready) until the reader switches back or upgrades.
/// The kill switch returns a pinned choice to the Omi socket.
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

  /// True when the persisted config is the free plan's pinned phone choice ([PhoneTranscriptionChoice]).
  final bool Function() pinnedReader;

  /// Persists the automatic switch at the cap as the phone choice and returns the persisted config.
  final Future<CustomSttConfig> Function(CustomSttConfig config) adoptPhoneChoice;

  SttModeResolver({
    bool Function()? flagReader,
    TranscriptionAllowanceSnapshot? Function()? allowanceReader,
    Future<FreemiumReadiness> Function({String? language})? readinessReader,
    CustomSttConfig? Function()? onDeviceConfigBuilder,
    Future<bool> Function()? killSwitchReader,
    void Function({String? language})? prepareOnDevice,
    bool Function()? pinnedReader,
    Future<CustomSttConfig> Function(CustomSttConfig config)? adoptPhoneChoice,
  })  : flagReader = flagReader ?? _defaultFlag,
        pinnedReader = pinnedReader ?? (() => PhoneTranscriptionChoice.isPinned(SharedPreferencesUtil())),
        adoptPhoneChoice =
            adoptPhoneChoice ?? ((config) => PhoneTranscriptionChoice.adopt(config, SharedPreferencesUtil())),
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

  /// An at-cap snapshot older than this no longer proves the cap (an upgrade outside the app,
  /// a new month): the session keeps today's Omi socket until the subscription refreshes.
  static const onDeviceSnapshotMaxAge = Duration(hours: 24);

  static TranscriptionAllowanceSnapshot? _defaultAllowance() {
    final snapshot = TranscriptionAllowanceCache.current;
    if (snapshot == null || !snapshot.isOnDevice) return snapshot;
    return TranscriptionAllowanceCache.currentWithin(onDeviceSnapshotMaxAge);
  }

  static Future<FreemiumReadiness> _defaultReadiness({String? language}) =>
      FreemiumTranscriptionService().checkReadiness(language: language);

  static CustomSttConfig? _defaultOnDeviceConfig() {
    final service = FreemiumTranscriptionService();
    if (service.readiness != FreemiumReadiness.ready) return null;
    final config = service.createOnDeviceSttConfig(
      language: FreemiumTranscriptionService.liveOnDeviceLanguage(),
      modelPath: service.cachedModelPath,
    );
    return config.copyWith(identity: freemiumOnDeviceId, sendRawAudioToOmi: false);
  }

  Future<SttModeDecision> decide({required CustomSttConfig persistedCustomStt, required BleAudioCodec codec}) async {
    FreemiumReadiness readiness = FreemiumReadiness.ready;
    final pinned = pinnedReader();
    // The kill switch never governs a Custom STT the reader set up themselves; only read it when
    // the free-tier route (or its pinned phone choice) is in play.
    final freeTierOn = flagReader() && (pinned || !persistedCustomStt.isEnabled) && !await killSwitchReader();
    // The kill switch also returns a pinned phone choice to today's Omi socket (the server holds
    // the audio at the cap); the pin itself is kept for when the switch is lifted.
    if (pinned && !freeTierOn) persistedCustomStt = CustomSttConfig.defaultConfig;
    final flag = freeTierOn && !persistedCustomStt.isEnabled;
    final allowance = allowanceReader();
    if ((persistedCustomStt.provider == SttProvider.onDeviceWhisper &&
            !kIsWeb &&
            defaultTargetPlatform == TargetPlatform.iOS) ||
        (flag && !persistedCustomStt.isEnabled && _needsOnDeviceReadiness(allowance))) {
      readiness = await readinessReader(
          language: persistedCustomStt.isEnabled && persistedCustomStt.provider == SttProvider.onDeviceWhisper
              ? persistedCustomStt.language
              : FreemiumTranscriptionService.liveOnDeviceLanguage());
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
    if (decision.path == SttResolvedPath.onDevice && decision.customSttConfig != null) {
      // The switch at the cap is permanent (David, 2026-11-16): persist it now, before the socket
      // opens, so every later decision is the same persisted config and never flips mid-session.
      final persisted = await adoptPhoneChoice(decision.customSttConfig!);
      return SttModeDecision(
        path: SttResolvedPath.onDevice,
        customSttConfig: persisted,
        reason: decision.reason,
        allowanceOnDevice: true,
      );
    }
    return decision;
  }

  /// True only for an exact `on_device` answer with a real (not transient) reason. An unknown
  /// future mode is not proof of the cap and keeps today's socket.
  static bool wantsOnDevice(TranscriptionAllowanceSnapshot? allowance) {
    if (allowance == null || !allowance.isOnDevice) return false;
    return !transientAllowanceReasons.contains(allowance.reason);
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
      // managed, an unknown mode, or on_device for a transient lookup failure (not spent minutes).
      return SttModeDecision(
        path: SttResolvedPath.managed,
        reason: allowance.isManaged || allowance.isOnDevice ? allowance.reason : 'allowance_unrecognized',
      );
    }

    // on_device for spent minutes: the phone transcribes when it can.
    final onDeviceReason = allowance.reason;
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
