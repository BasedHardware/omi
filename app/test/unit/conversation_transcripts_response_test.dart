import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';

Map<String, dynamic> _segment(String text) => {
      'id': text,
      'text': text,
      'speaker': 'SPEAKER_00',
      'is_user': false,
      'start': 0,
      'end': 1,
      'translations': <Map<String, dynamic>>[],
      'speech_profile_processed': true,
    };

void main() {
  test('TranscriptsResponse tolerates missing provider lists', () {
    final response = TranscriptsResponse.fromJson({
      'deepgram': [_segment('hello')],
    });

    expect(response.deepgram.single.text, 'hello');
    expect(response.soniox, isEmpty);
    expect(response.whisperx, isEmpty);
    expect(response.speechmatics, isEmpty);
  });
}
