import 'dart:convert';
import 'dart:typed_data';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/logger.dart';

/// Raised when the TTS endpoint is temporarily unavailable (503) or the user
/// is rate-limited (429). Callers should degrade gracefully — either skip
/// audio playback for this response or fall back to on-device TTS.
class TtsUnavailableException implements Exception {
  final int statusCode;
  final String? retryAfter;
  TtsUnavailableException(this.statusCode, {this.retryAfter});

  @override
  String toString() =>
      'TtsUnavailableException(status=$statusCode${retryAfter != null ? ', retryAfter=$retryAfter' : ''})';
}

/// Calls `POST /v2/tts/synthesize` and returns the raw MP3 bytes.
///
/// Defaults mirror the desktop client and the Rust backend at
/// `desktop/Backend-Rust/src/routes/tts.rs` so both platforms stay in sync.
Future<Uint8List?> synthesizeSpeech({
  required String text,
  String voiceId = 'BAMYoBHLZM7lJgJAmFz0', // Sloane
  String modelId = 'eleven_turbo_v2_5',
  String outputFormat = 'mp3_44100_128',
  Map<String, dynamic>? voiceSettings,
}) async {
  final Map<String, dynamic> body = {
    'text': text,
    'voice_id': voiceId,
    'model_id': modelId,
    'output_format': outputFormat,
  };
  if (voiceSettings != null) {
    body['voice_settings'] = voiceSettings;
  }

  final response = await makeApiCall(
    url: '${Env.apiBaseUrl}v2/tts/synthesize',
    headers: {},
    method: 'POST',
    body: jsonEncode(body),
    // TTS is a background-effect endpoint; a transient 401 here must NOT
    // log the user out of the entire app. Surface as a non-200 instead so
    // playback degrades gracefully.
    signOutOn401: false,
  );

  if (response == null) {
    throw TtsUnavailableException(0);
  }

  if (response.statusCode == 429 || response.statusCode == 503) {
    throw TtsUnavailableException(
      response.statusCode,
      retryAfter: response.headers['retry-after'],
    );
  }

  if (response.statusCode != 200) {
    Logger.log('synthesizeSpeech: non-200 status=${response.statusCode} body=${response.body}');
    return null;
  }

  return response.bodyBytes;
}
