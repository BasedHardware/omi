import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/messages.dart';

void main() {
  group('voiceTranscriptionFailure', () {
    test('reads the typed outcome from a 502 body', () {
      final error = voiceTranscriptionFailure(
        502,
        '{"detail":{"error":"transcription_failed","outcome":"upstream_error","provider":"modulate",'
        '"retryable":true,"message":"Transcription failed"}}',
      );

      expect(error.statusCode, 502);
      expect(error.outcome, 'upstream_error');
      expect(error.retryable, isTrue);
      expect(error.isServerSide, isTrue);
    });

    test('keeps the status when a proxy answers with non-JSON', () {
      final error = voiceTranscriptionFailure(503, '<html>Service Unavailable</html>');

      expect(error.statusCode, 503);
      expect(error.outcome, isNull);
      expect(error.isServerSide, isTrue);
    });

    test('treats an invalid clip as a client-side failure', () {
      final error = voiceTranscriptionFailure(400, '{"detail":{"outcome":"invalid_input","retryable":false}}');

      expect(error.outcome, 'invalid_input');
      expect(error.isServerSide, isFalse);
    });

    test('treats rate limiting as server-side, but not a lost connection', () {
      expect(voiceTranscriptionFailure(429, '').isServerSide, isTrue);
      expect(const VoiceTranscriptionException(cause: 'SocketException').isServerSide, isFalse);
    });
  });
}
