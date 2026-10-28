import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:opus_dart/opus_dart.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/uplink_silence_timer.dart';
import 'package:omi/services/experiments/live_preview_gate.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_notes.dart';
import 'package:omi/services/freemium_transcription_service.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';
import 'package:omi/services/live_preview/whisper_window_preview_engine.dart';
import 'package:omi/services/sockets/on_device_whisper_provider.dart';

/// Production wiring: the native engine per platform (iOS
/// `LivePreviewPlugin.swift`, Android `LivePreviewPlugin.kt`); on Android,
/// Omi's downloaded Whisper model is the windowed fallback. Other platforms
/// have no preview controller, so they never declare `local_preview=enabled`.
LivePreviewController? composeLivePreview() {
  if (!Platform.isIOS && !Platform.isAndroid) return null;
  SimpleOpusDecoder? decoder;
  final android = Platform.isAndroid;
  final controller = LivePreviewController(
    engine: android
        ? FallbackLivePreviewEngine(primary: MethodChannelLivePreviewEngine(), fallback: _downloadedWhisper)
        : MethodChannelLivePreviewEngine(),
    telemetry: LivePreviewTelemetry(),
    platform: android ? LivePreviewPlatform.android : LivePreviewPlatform.ios,
    osMajor: android ? 0 : osMajorVersion(Platform.operatingSystemVersion),
    // On-device live notes: Apple Foundation Models on iOS 26+; Android has no
    // engine in this release (the Summary shows the quiet line).
    notesEngine: android ? noLivePreviewNotesEngine : methodChannelLivePreviewNotes,
    // A preview-only decoder: capture's Opus bytes are copied before decoding.
    decodeOpus: (Uint8List opus) => (decoder ??= SimpleOpusDecoder(sampleRate: 16000, channels: 1)).decode(input: opus),
    conversationGap: () => UplinkSilenceTimer.fromPreference(SharedPreferencesUtil().conversationSilenceDuration),
    requestAllowed: LivePreviewGate.requestAllowed,
  );
  if (android) {
    unawaited(DeviceInfoPlugin()
        .androidInfo
        .then((info) => controller.osMajor = osMajorVersion(info.version.release))
        .catchError((Object _) => 0));
  }
  return controller;
}

/// The Whisper model the user already downloaded for on-device transcription,
/// or null. Never downloads one.
Future<LivePreviewEngine?> _downloadedWhisper() async {
  final service = FreemiumTranscriptionService();
  await service.checkReadiness();
  final model = service.cachedModelPath;
  if (model == null) return null;
  final whisper = OnDeviceWhisperProvider(modelPath: model, onDeviceOverflowEnabled: false);
  return WhisperWindowPreviewEngine(
    transcribe: (wav, language) async => (await whisper.transcribe(wav, language: language))?.rawText,
  );
}

/// First integer in an OS version string ("Version 26.1 (Build 23B85)" → 26).
int osMajorVersion(String version) => int.tryParse(RegExp(r'\d+').firstMatch(version)?.group(0) ?? '') ?? 0;
