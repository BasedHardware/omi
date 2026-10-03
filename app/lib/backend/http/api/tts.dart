import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Raised when the TTS endpoint is temporarily unavailable (503), the user is
/// rate-limited (429), or the request failed before audio arrived (status 0).
class TtsUnavailableException implements Exception {
  final int statusCode;
  final String? retryAfter;
  TtsUnavailableException(this.statusCode, {this.retryAfter});

  @override
  String toString() =>
      'TtsUnavailableException(status=$statusCode${retryAfter != null ? ', retryAfter=$retryAfter' : ''})';
}

/// A response body that can be consumed while the TTS server is still writing
/// it. [contentLength] is absent for chunked responses.
class TtsAudioStream {
  final Stream<List<int>> bytes;
  final int? contentLength;
  final String contentType;
  final Future<void> Function() cancel;

  const TtsAudioStream({
    required this.bytes,
    required this.contentLength,
    required this.contentType,
    required this.cancel,
  });
}

/// Starts immediately and remains cancellable both before response headers and
/// while the response body is streaming.
class TtsSynthesisRequest {
  final Future<TtsAudioStream?> response;
  final Future<void> Function() cancel;

  const TtsSynthesisRequest({required this.response, required this.cancel});
}

/// Starts `POST /v2/tts/synthesize` without materializing the response body.
///
/// Defaults mirror the desktop client and backend so both platforms stay in
/// sync. The abort trigger is shared with package:http's request and response,
/// which makes stop/new-query/background cancellation close the socket even if
/// the server has not sent headers yet.
TtsSynthesisRequest synthesizeSpeechStream({
  required String text,
  String voiceId = 'BAMYoBHLZM7lJgJAmFz0', // Sloane
  String modelId = 'eleven_turbo_v2_5',
  String outputFormat = 'mp3_44100_128',
  Map<String, dynamic>? voiceSettings,
}) {
  final body = <String, dynamic>{
    'text': text,
    'voice_id': voiceId,
    'model_id': modelId,
    'output_format': outputFormat,
    if (voiceSettings != null) 'voice_settings': voiceSettings,
  };
  final abort = Completer<void>();

  Future<void> cancel() async {
    if (!abort.isCompleted) abort.complete();
  }

  Future<TtsAudioStream?> send() async {
    try {
      final response = await makeRawApiCall(
        url: '${Env.apiBaseUrl}v2/tts/synthesize',
        headers: const {},
        method: 'POST',
        body: jsonEncode(body),
        // TTS is a background effect. A transient 401 must not sign the user
        // out of the app; playback degrades to the system voice instead.
        signOutOn401: false,
        abortTrigger: abort.future,
        timeout: const Duration(seconds: 30),
      );

      if (response.statusCode == 429 || response.statusCode == 503) {
        await cancel();
        throw TtsUnavailableException(response.statusCode, retryAfter: response.headers['retry-after']);
      }

      if (response.statusCode != 200) {
        Logger.log('synthesizeSpeechStream: non-200 status=${response.statusCode}');
        await cancel();
        return null;
      }

      return TtsAudioStream(
        bytes: response.stream,
        contentLength: response.contentLength,
        contentType: response.headers['content-type'] ?? 'audio/mpeg',
        cancel: cancel,
      );
    } on http.RequestAbortedException {
      rethrow;
    } on TtsUnavailableException {
      rethrow;
    } catch (e, stackTrace) {
      Logger.debug('synthesizeSpeechStream failed before audio: $e, $stackTrace');
      throw TtsUnavailableException(0);
    }
  }

  return TtsSynthesisRequest(response: send(), cancel: cancel);
}

/// Collects a full `POST /v2/tts/synthesize` body into memory.
///
/// Phone streaming prefers [synthesizeSpeechStream]. The DevKit 2 wearable
/// speaker path needs this helper so it can request `pcm_16000` (signed 16-bit
/// LE mono), downsample to 8 kHz, and write over BLE.
Future<Uint8List?> synthesizeSpeech({
  required String text,
  String voiceId = 'BAMYoBHLZM7lJgJAmFz0', // Sloane
  String modelId = 'eleven_turbo_v2_5',
  String outputFormat = 'mp3_44100_128',
  Map<String, dynamic>? voiceSettings,
}) async {
  final request = synthesizeSpeechStream(
    text: text,
    voiceId: voiceId,
    modelId: modelId,
    outputFormat: outputFormat,
    voiceSettings: voiceSettings,
  );
  final audio = await request.response;
  if (audio == null) return null;

  final builder = BytesBuilder(copy: false);
  await for (final chunk in audio.bytes) {
    builder.add(chunk);
  }
  final bytes = builder.takeBytes();
  return bytes.isEmpty ? null : bytes;
}
