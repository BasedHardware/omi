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

TranscriptSegment _segment(String id, String text, {int speakerId = 0}) {
  return TranscriptSegment(
    id: id,
    text: text,
    speaker: 'SPEAKER_0$speakerId',
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

  group('speaker label suggestion handling', () {
    test('applies assignment locally when person_id is present', () {
      final provider = CaptureProvider();
      final seg = _segment('seg1', 'hello', speakerId: 1);
      provider.segments = [seg];

      // Simulate backend-assigned suggestion (has person_id)
      final event = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person123',
        personName: 'Alice',
        segmentId: 'seg1',
      );

      provider.onMessageEventReceived(event);

      // Should apply locally - segment gets person_id
      expect(provider.segments.first.personId, 'person123');
      expect(provider.segments.first.isUser, false);
      // Should NOT store in suggestions (no Tag UI needed)
      expect(provider.suggestionsBySegmentId.containsKey('seg1'), false);
    });

    test('stores suggestion when person_id is empty', () {
      final provider = CaptureProvider();
      final seg = _segment('seg2', 'world', speakerId: 2);
      provider.segments = [seg];

      // Simulate suggestion without person_id (needs manual tagging)
      final event = SpeakerLabelSuggestionEvent(
        speakerId: 2,
        personId: '',
        personName: 'Unknown',
        segmentId: 'seg2',
      );

      provider.onMessageEventReceived(event);

      // Should NOT apply locally - segment stays unassigned
      expect(provider.segments.first.personId, null);
      // Should store in suggestions (Tag UI needed)
      expect(provider.suggestionsBySegmentId.containsKey('seg2'), true);
    });

    test('clears existing suggestions when backend assigns speaker', () {
      final provider = CaptureProvider();
      final seg1 = _segment('seg1', 'hello', speakerId: 1);
      final seg2 = _segment('seg2', 'world', speakerId: 1);
      provider.segments = [seg1, seg2];

      // Pre-existing suggestion
      provider.suggestionsBySegmentId['old'] = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: '',
        personName: 'Old',
        segmentId: 'old',
      );

      // Backend assigns speaker 1
      final event = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'person123',
        personName: 'Alice',
        segmentId: 'seg1',
      );

      provider.onMessageEventReceived(event);

      // Old suggestion for same speaker should be cleared
      expect(provider.suggestionsBySegmentId.containsKey('old'), false);
      // Both segments with speakerId=1 should be assigned
      expect(provider.segments[0].personId, 'person123');
      expect(provider.segments[1].personId, 'person123');
    });

    test('handles user assignment via person_id=user', () {
      final provider = CaptureProvider();
      final seg = _segment('seg1', 'hello', speakerId: 1);
      provider.segments = [seg];

      final event = SpeakerLabelSuggestionEvent(
        speakerId: 1,
        personId: 'user',
        personName: 'User',
        segmentId: 'seg1',
      );

      provider.onMessageEventReceived(event);

      expect(provider.segments.first.isUser, true);
      expect(provider.segments.first.personId, null);
    });
  });
}
