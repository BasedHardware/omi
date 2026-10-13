import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/capture_controller.dart';
import 'package:omi/services/capture/capture_external_actions.dart';
import 'package:omi/services/capture/capture_seams.dart';

class _Actions extends NoopCaptureExternalActions {
  int created = 0;
  int assigned = 0;
  @override
  Future<Person?> createPerson(String name) async {
    created++;
    return null;
  }

  @override
  Future<bool> assignSpeaker(String id, List<String> ids, String person, {int? speakerId}) async {
    assigned++;
    return true;
  }
}

class _Ble implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}
  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

TranscriptSegment _segment(String id) => TranscriptSegment(
    id: id, text: 'TV', speaker: 'SPEAKER_04', isUser: true, personId: null, start: 0, end: 2, translations: []);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    SharedPreferences.setMockInitialValues({'deviceMuted': true});
    await SharedPreferencesUtil.init();
  });
  test('exclusion clears the cluster, skips person creation, suppresses suggestions and is reversible', () async {
    final actions = _Actions();
    final calls = <List<String>>[];
    var succeeds = true;
    final controller = CaptureController(
      externalActions: actions,
      bleListeners: _Ble(),
      connectivity: CaptureConnectivityBoundary(
        initiallyConnected: true,
        changes: const Stream.empty(),
        isConnected: () => true,
      ),
      excludeSpeaker: (id, ids) async {
        expect(id, 'c');
        calls.add(ids);
        return succeeds;
      },
    );
    addTearDown(() async {
      controller.dispose();
      await controller.lifetime.close();
    });
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'c',
        createdAt: DateTime(2026),
        structured: Structured('TV', 'TV'),
        transcriptSegments: [_segment('s1'), _segment('s2')],
      ),
    );
    final suggestion = SpeakerLabelSuggestionEvent(speakerId: 4, personId: '', personName: 'Sam', segmentId: 's2');
    controller.suggestionsBySegmentId['s2'] = suggestion;
    succeeds = false;
    expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isFalse);
    expect(controller.segments.first.isUser, isTrue);
    expect(controller.suggestionsBySegmentId, isNotEmpty);
    succeeds = true;
    for (var i = 0; i < 2; i++) {
      expect(await controller.assignSpeakerToConversation(4, '', '', ['s1'], notAPerson: true), isTrue);
      expect(controller.segments.every((s) => !s.isUser && s.personId == null && s.speakerLabelSource == null), isTrue);
      expect(controller.suggestionsBySegmentId, isEmpty);
      controller.onMessageEventReceived(suggestion);
      expect(controller.suggestionsBySegmentId, isEmpty);
    }
    expect(calls.every((ids) => ids.length == 2), isTrue);
    expect(actions.created, 0);
    expect(actions.assigned, 0);
    controller.onSegmentReceived([_segment('later')]);
    await Future<void>.delayed(Duration.zero);
    expect(controller.segments.every((s) => !s.isUser && s.personId == null), isTrue);
    for (final person in ['p1', 'user']) {
      expect(
        await controller.assignSpeakerToConversation(4, person, 'Sam', ['s1', 's2'], applyToSpeaker: true),
        isTrue,
      );
      expect(
        controller.segments.every(
          (s) => s.isUser == (person == 'user') && s.personId == (person == 'user' ? null : person),
        ),
        isTrue,
      );
    }
    controller.applyInProgressConversation(
      ServerConversation(
        id: 'next',
        createdAt: DateTime(2026),
        structured: Structured('next', 'next'),
        transcriptSegments: [_segment('s2')..isUser = false],
      ),
    );
    controller.onMessageEventReceived(suggestion);
    expect(controller.suggestionsBySegmentId, isNotEmpty);
  });
}
