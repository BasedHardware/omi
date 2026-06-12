import 'dart:typed_data';

import 'package:omi/models/stt_result.dart';
import 'package:omi/services/custom_stt_log_service.dart';
import 'package:omi/services/sockets/pure_polling.dart';

class OnDeviceWhisperProvider implements ISttProvider {
  final String modelPath;
  final String language;

  OnDeviceWhisperProvider({required this.modelPath, this.language = 'en'});

  @override
  Future<SttTranscriptionResult?> transcribe(
    Uint8List audioData, {
    double audioOffsetSeconds = 0,
    String? language,
  }) async {
    CustomSttLogService.instance.warning(
      'OnDeviceWhisper',
      'On-device Whisper is unavailable on this platform because it requires native FFI bindings.',
    );
    return null;
  }

  @override
  void dispose() {}
}
