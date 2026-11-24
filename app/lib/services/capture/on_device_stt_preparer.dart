import 'dart:async';
import 'dart:io';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import 'package:omi/models/transcription_allowance.dart';
import 'package:omi/services/capture/stt_mode_resolver.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/on_device/on_device_model.dart';
import 'package:omi/services/sockets/on_device_apple_provider.dart';
import 'package:omi/utils/logger.dart';

/// Gets the live on-device speech model onto the phone before the plan's cloud minutes run out,
/// so the switch to on-device transcription at the cap is seamless.
///
/// iOS: asks Apple to install its speech assets (OS-managed, no Omi download), never the permission.
/// Android: downloads the Whisper model the live on-device provider reads, on Wi-Fi only.
/// Best effort and single-flight; failures are logged and retried on the next trigger.
abstract final class OnDeviceSttPreparer {
  /// Start preparing once this little managed time is left (or none at all).
  static const prepareBelowRemainingSeconds = 2 * 60 * 60;

  static Future<void>? _inFlight;

  @visibleForTesting
  static Future<void> Function({String? language})? debugOverride;

  /// True when [allowance] says the cloud minutes are spent or nearly spent.
  static bool shouldPrepareFor(TranscriptionAllowanceSnapshot? allowance) {
    if (allowance == null) return false;
    if (allowance.isOnDevice) return !SttModeResolver.transientAllowanceReasons.contains(allowance.reason);
    if (!allowance.isManaged) return false;
    final remaining = allowance.remainingSeconds;
    return remaining != null && remaining <= prepareBelowRemainingSeconds;
  }

  static void prepare({String? language}) => unawaited(prepareAndWait(language: language));

  /// [prepare], for a caller that acts once the model is here (Android "On Wi-Fi later").
  static Future<void> prepareAndWait({String? language}) =>
      _inFlight ??= (debugOverride ?? _prepare)(language: language).whenComplete(() => _inFlight = null);

  static Future<void> _prepare({String? language}) async {
    try {
      if (Platform.isIOS) {
        // Apple's asset install has no Wi-Fi guard of its own; never spend cellular data on it.
        if (!(await Connectivity().checkConnectivity()).contains(ConnectivityResult.wifi)) return;
        final lang = language ?? FreemiumTranscriptionService.liveOnDeviceLanguage();
        // A plain readiness check installs Apple's assets but never asks for speech-recognition
        // permission: a background prompt has no context. Settings › Transcription asks for it.
        final readiness = await OnDeviceAppleProvider.readiness(lang);
        Logger.debug('[OnDevicePrep] iOS speech ${readiness.engine}: ${readiness.status}');
      } else if (Platform.isAndroid) {
        final model = WhisperOnDeviceModel();
        await model.refresh();
        if (model.status.phase != OnDeviceModelPhase.installed) {
          await model.download(wifiOnly: true);
        }
        Logger.debug('[OnDevicePrep] Android whisper: ${model.status.phase.name}');
      } else {
        return;
      }
      await FreemiumTranscriptionService()
          .checkReadiness(language: language ?? FreemiumTranscriptionService.liveOnDeviceLanguage());
    } catch (e) {
      Logger.debug('[OnDevicePrep] prepare failed: $e');
    }
  }
}
