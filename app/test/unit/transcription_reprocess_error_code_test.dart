import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';

void main() {
  test('maps stable missing audio and empty speech codes regardless of wording', () {
    for (final code in ['no_audio', 'no_speech']) {
      expect(transcriptionReprocessErrorCode(400, '{"detail":{"code":"$code","message":"Changed copy"}}'), 'no_audio');
      expect(transcriptionReprocessErrorCode(400, '{"detail":{"code":"$code"}}'), 'no_audio');
    }
  });

  test('storage/server failures cannot be misclassified as missing audio', () {
    expect(transcriptionReprocessErrorCode(502, '{"detail":{"code":"no_audio"}}'), 'failed');
    expect(transcriptionReprocessErrorCode(400, '{"detail":{"code":"failed","message":"no stored audio"}}'), 'failed');
    expect(transcriptionReprocessErrorCode(400, '{"detail":"no speech"}'), 'failed');
  });

  test('malformed and unknown responses remain generic failures', () {
    for (final body in [
      '',
      'not json',
      'null',
      '[]',
      '{}',
      '{"detail":null}',
      '{"detail":[]}',
      '{"detail":{}}',
      '{"detail":{"code":42}}',
      '{"detail":{"code":null}}',
      '{"detail":{"code":"future_code"}}',
    ]) {
      expect(transcriptionReprocessErrorCode(400, body), 'failed');
    }
    expect(transcriptionReprocessErrorCode(null, ''), 'failed');
    expect(transcriptionReprocessErrorCode(500, 'boom'), 'failed');
  });
}
