import 'package:pigeon/pigeon.dart';

// Dedicated contract for the native iOS phone-mic capture module. Kept separate
// from pigeon_interfaces.dart so the module owns its generated files end to end.
// Regenerate with: dart run pigeon --input lib/phone_mic_interface.dart
@ConfigurePigeon(
  PigeonOptions(
    dartOut: 'lib/gen/phone_mic_pigeon.g.dart',
    dartOptions: DartOptions(),
    swiftOut: 'ios/Runner/PhoneMic/PhoneMicPigeon.g.swift',
    // The shared PigeonCommunicator.g.swift already defines `PigeonError`; a
    // second generated file with the default error class name would collide.
    swiftOptions: SwiftOptions(errorClassName: 'PhoneMicPigeonError'),
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

/// Dart -> native. start() resolves once the engine is running, or throws a
/// PlatformException with one of: permission_denied, session_config_failed,
/// format_invalid, converter_init_failed, engine_start_failed. stop() resolves
/// only after teardown is fully drained — no frames or events arrive after it.
@HostApi()
abstract class PhoneMicHostApi {
  @async
  void start();

  @async
  void stop();

  bool isRecording();
}

/// Native -> Dart.
@FlutterApi()
abstract class PhoneMicFlutterApi {
  /// PCM16 little-endian mono @16kHz. Chunk sizes vary with the input route.
  void onAudioFrame(Uint8List pcm16leMono16k);

  void onStateChanged(PhoneMicCaptureState state);

  /// Non-fatal runtime failures (capture self-heals): converter_failed,
  /// rebuild_failed, resume_failed, media_services_reset.
  void onCaptureError(String code, String message);
}
