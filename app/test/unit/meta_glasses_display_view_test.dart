import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/meta_wearables_provider.dart';

void main() {
  group('Meta glasses display view', () {
    test('builds status-only card when no transcript exists', () {
      final view = MetaWearablesProvider.buildDisplayCaptureView(captureStateLine: 'Listening').toJson();

      expect(view['type'], 'flexBox');
      expect(view['padding'], 16);
      expect(view['children'], [
        {'type': 'text', 'text': 'Listening', 'style': 'heading'},
      ]);
    });

    test('adds latest transcript snippet and truncates it for the lens', () {
      final longText = 'This is a long transcript segment that should be compact enough for the small display '
          'surface instead of wrapping forever on the lens.';

      final view = MetaWearablesProvider.buildDisplayCaptureView(
        captureStateLine: 'Listening',
        segments: [
          _segment('older text'),
          _segment(longText),
        ],
      ).toJson();

      final children = view['children']! as List<Object?>;
      expect(children, hasLength(2));
      expect(children.last, {
        'type': 'text',
        'text': 'This is a long transcript segment that should be compact enough for the small...',
        'style': 'body',
        'color': 'secondary',
      });
    });
  });
}

TranscriptSegment _segment(String text) {
  return TranscriptSegment(
    id: text,
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0,
    end: 1,
    translations: [],
  );
}
