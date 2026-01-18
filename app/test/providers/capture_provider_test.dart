import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/services.dart';

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async {
    return [ConnectivityResult.none];
  }

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

TranscriptSegment _segment(String id, String text) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0.0,
    end: 1.0,
    translations: [],
  );
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {
      // Ignore if already initialized by another test.
    }
  });

  test('removes segments and related state on deletion event', () {
    final provider = CaptureProvider();
    final first = _segment('a', 'one');
    final second = _segment('b', 'two');

    provider.segments = [first, second];
    provider.suggestionsBySegmentId['a'] = SpeakerLabelSuggestionEvent(
      speakerId: 1,
      personId: 'p1',
      personName: 'Test',
      segmentId: 'a',
    );
    provider.taggingSegmentIds = ['a', 'b'];
    provider.hasTranscripts = true;

    provider.onMessageEventReceived(SegmentsDeletedEvent(segmentIds: ['a']));

    expect(provider.segments.length, 1);
    expect(provider.segments.first.id, 'b');
    expect(provider.suggestionsBySegmentId.containsKey('a'), false);
    expect(provider.taggingSegmentIds.contains('a'), false);
    expect(provider.hasTranscripts, true);
  });
}
