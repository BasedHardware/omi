import 'package:pigeon/pigeon.dart';

// Dedicated contract for the native phone-mic capture modules (iOS and Android).
// Kept separate from pigeon_interfaces.dart so the module owns its generated files end to end.
// Regenerate with: dart run pigeon --input lib/phone_mic_interface.dart
@ConfigurePigeon(
  PigeonOptions(
    dartOut: 'lib/gen/phone_mic_pigeon.g.dart',
    dartOptions: DartOptions(),
    swiftOut: 'ios/Runner/PhoneMic/PhoneMicPigeon.g.swift',
    // The shared PigeonCommunicator.g.swift already defines `PigeonError`; a
    // second generated file with the default error class name would collide.
    swiftOptions: SwiftOptions(errorClassName: 'PhoneMicPigeonError'),
    kotlinOut: 'android/app/src/main/kotlin/com/friend/ios/phonemic/PhoneMicPigeon.g.kt',
    // PigeonCommunicator.g.kt (package com.friend.ios) already declares the default
    // FlutterError; an own package + error class keeps the two generated files disjoint.
    kotlinOptions: KotlinOptions(package: 'com.friend.ios.phonemic', errorClassName: 'PhoneMicPigeonError'),
    dartPackageName: 'omi_phone_mic',
  ),
)

/// Native capture state machine, mirrored to Dart on every transition.
enum PhoneMicCaptureState {
  idle,
  starting,
  running,
  interrupted,
  rebuilding,
}

/// Capture sink selector, chosen once per session at start().
///
/// - stream: converted PCM16 chunks are forwarded to Dart via onAudioFrame for
///   realtime transcription (the existing path).
/// - batch: converted PCM16 chunks are opus-encoded natively and written to
///   WAL-compatible .bin files on disk; nothing is sent to Dart except state and
///   onBatchProgress. Used for "transcribe later" offline capture.
enum PhoneMicCaptureMode {
  stream,
  batch,
}

/// Dart -> native. start(mode, sessionId) resolves once the engine is running, or
/// throws a PlatformException with one of: permission_denied,
/// session_config_failed, format_invalid, converter_init_failed,
/// engine_start_failed. In batch mode it may additionally throw opus_init_failed
/// (the native opus encoder could not be created) or batch_dir_unavailable
/// (flutter.batchAudioDir is unset/empty).
///
/// `sessionId` is a Dart-minted, monotonically increasing identity for this
/// capture session. Every FlutterApi event carries the id of the session it
/// belongs to; Dart drops any event whose id does not match its current session.
/// A start() arriving while a native session is already live ADOPTS the new id
/// (all future events for that live session carry it) and immediately re-emits the
/// current state under it — so the caller always converges to the real state even
/// after a de-sync. The session's mode is fixed at its original start and a late
/// start() cannot re-select it.
///
/// stop() resolves only after teardown is fully drained — no frames or events
/// arrive after it, and in batch mode the current .bin file is finalized (fsynced
/// + atomically promoted, so it is ingestable) before stop() resolves. stop() is
/// safe to call regardless of session state (it resolves harmlessly when idle).
@HostApi()
abstract class PhoneMicHostApi {
  @async
  void start(PhoneMicCaptureMode mode, int sessionId);

  @async
  void stop();

  bool isRecording();
}

/// Native -> Dart. Every method carries the `sessionId` of the session the event
/// belongs to; Dart drops any event whose id does not match its current session.
@FlutterApi()
abstract class PhoneMicFlutterApi {
  /// PCM16 little-endian mono @16kHz. Chunk sizes vary with the input route.
  /// Stream mode only; batch mode never emits frames. A frame belongs to the
  /// session that was current when its capture epoch was built.
  void onAudioFrame(Uint8List pcm16leMono16k, int sessionId);

  void onStateChanged(PhoneMicCaptureState state, int sessionId);

  /// Non-fatal runtime failures (capture self-heals): converter_failed,
  /// rebuild_failed, resume_failed, media_services_reset, batch_storage_full.
  void onCaptureError(String code, String message, int sessionId);

  /// Emitted at 1Hz while batch capture runs. Its arrival is the liveness signal
  /// for the Dart batch watchdog; the value is derived from the number of frames
  /// actually written to disk, so mutes and interruptions freeze it while the
  /// event keeps arriving.
  void onBatchProgress(double capturedSeconds, int sessionId);
}
