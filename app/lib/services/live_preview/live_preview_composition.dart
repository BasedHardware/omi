import 'dart:io';
import 'dart:typed_data';

import 'package:opus_dart/opus_dart.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/capture/uplink_silence_timer.dart';
import 'package:omi/services/experiments/live_preview_gate.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/services/live_preview/live_preview_telemetry.dart';

/// Production wiring. Phase 1 ships the iOS native engine only; on other
/// platforms there is no preview controller, so the client never declares
/// `local_preview=enabled` and keeps today's cloud live transcript.
LivePreviewController? composeLivePreview() {
  if (!Platform.isIOS) return null;
  SimpleOpusDecoder? decoder;
  return LivePreviewController(
    engine: MethodChannelLivePreviewEngine(),
    telemetry: LivePreviewTelemetry(),
    platform: LivePreviewPlatform.ios,
    osMajor: osMajorVersion(Platform.operatingSystemVersion),
    // A preview-only decoder: capture's Opus bytes are copied before decoding.
    decodeOpus: (Uint8List opus) => (decoder ??= SimpleOpusDecoder(sampleRate: 16000, channels: 1)).decode(input: opus),
    conversationGap: () => UplinkSilenceTimer.fromPreference(SharedPreferencesUtil().conversationSilenceDuration),
    requestAllowed: LivePreviewGate.requestAllowed,
  );
}

/// First integer in an OS version string ("Version 26.1 (Build 23B85)" → 26).
int osMajorVersion(String version) => int.tryParse(RegExp(r'\d+').firstMatch(version)?.group(0) ?? '') ?? 0;
