import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/conversations.dart';

void main() {
  test('reads prerecorded transcript segments from the response', () {
    final response = TranscriptsResponse.fromGeneratedWireJson({
      'prerecorded': [
        {
          'end': 2.0,
          'is_user': false,
          'start': 1.0,
          'text': 'recorded',
        },
      ],
    });

    expect(response.prerecorded, hasLength(1));
    expect(response.prerecorded.single.text, 'recorded');
    expect(response.prerecorded.single.start, 1.0);
    expect(response.prerecorded.single.end, 2.0);
  });
}
