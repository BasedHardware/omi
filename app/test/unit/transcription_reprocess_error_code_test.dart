import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';

void main() {
  test('maps missing stored audio and empty STT to no_audio', () {
    expect(transcriptionReprocessErrorCode(400, 'No stored audio available to retranscribe'), 'no_audio');
    expect(transcriptionReprocessErrorCode(400, '{"detail":"Transcription produced no speech"}'), 'no_audio');
  });

  test('maps other failures to failed', () {
    expect(transcriptionReprocessErrorCode(null, ''), 'failed');
    expect(transcriptionReprocessErrorCode(502, 'Transcription provider failed'), 'failed');
    expect(transcriptionReprocessErrorCode(500, 'boom'), 'failed');
    expect(transcriptionReprocessErrorCode(400, 'App does not support conversation summarization'), 'failed');
  });
}
