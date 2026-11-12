import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/messages.dart';

void main() {
  group('VoiceTranscriptionException', () {
    test('a 5xx is a server-side fault, so the recording can be retried later', () {
      expect(const VoiceTranscriptionException(statusCode: 502).isServerSide, isTrue);
      expect(const VoiceTranscriptionException(statusCode: 503).isServerSide, isTrue);
    });

    test('rate limiting is server-side', () {
      expect(const VoiceTranscriptionException(statusCode: 429).isServerSide, isTrue);
    });

    test('an invalid clip and a lost connection are not reported as our fault', () {
      expect(const VoiceTranscriptionException(statusCode: 400).isServerSide, isFalse);
      expect(const VoiceTranscriptionException(cause: 'SocketException').isServerSide, isFalse);
    });

    test('an empty transcript is typed and not server-side', () {
      const error = VoiceTranscriptionException(statusCode: 200, outcome: 'empty_transcript', retryable: false);
      expect(error.isServerSide, isFalse);
      expect(error.toString(), contains('empty_transcript'));
    });
  });
}
