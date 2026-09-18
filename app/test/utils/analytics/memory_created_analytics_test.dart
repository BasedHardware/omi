import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
      appName: 'Omi Test',
      packageName: 'com.omi.test',
      version: '2.3.4',
      buildNumber: '567',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('Memory Created keeps memory_id and memory_result and does not derive counts from transcript text', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    final conversation = _conversation(id: 'mem-saved-1', discarded: false);
    AnalyticsManager().conversationCreated(conversation);
    await AnalyticsManager.flushPending(force: true);

    final payload = adapter.payloadFor('Memory Created');
    expect(payload['memory_id'], 'mem-saved-1');
    expect(payload['memory_result'], 'saved');
    expectNoTranscriptDerivedCounts(payload);
    expect(
      payload.values.whereType<String>().join(' '),
      isNot(contains('UNIQUE_ANALYTICS_TRANSCRIPT_TOKEN')),
    );
  });

  test('Memory Created discarded conversations still emit memory_result without transcript-derived counts', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    final conversation = _conversation(id: 'mem-discarded-1', discarded: true);
    AnalyticsManager().conversationCreated(conversation);
    await AnalyticsManager.flushPending(force: true);

    final payload = adapter.payloadFor('Memory Created');
    expect(payload['memory_id'], 'mem-discarded-1');
    expect(payload['memory_result'], 'discarded');
    expectNoTranscriptDerivedCounts(payload);
  });
}

const _transcriptDerivedKeys = {'transcript_length', 'transcript_word_count', 'speaker_count'};

void expectNoTranscriptDerivedCounts(Map<String, Object> properties) {
  expect(
    properties.keys.toSet().intersection(_transcriptDerivedKeys),
    isEmpty,
    reason: 'Memory Created must not emit counts derived by reading transcript text',
  );
}

ServerConversation _conversation({required String id, required bool discarded}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime.utc(2026, 1, 15),
    structured: Structured('Title', 'Overview'),
    discarded: discarded,
    source: ConversationSource.omi,
    startedAt: DateTime.utc(2026, 1, 15, 12),
    finishedAt: DateTime.utc(2026, 1, 15, 12, 0, 12),
    transcriptSegments: [
      TranscriptSegment(
        id: 'seg-0',
        text: 'UNIQUE_ANALYTICS_TRANSCRIPT_TOKEN secret words',
        speaker: 'SPEAKER_00',
        isUser: false,
        personId: null,
        start: 0,
        end: 12,
        translations: const [],
      ),
    ],
  );
}

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  final List<_RecordedEvent> events = [];
  bool _initialized = false;

  Map<String, Object> payloadFor(String eventName) {
    final match = events.where((event) => event.eventName == eventName);
    expect(match, hasLength(1), reason: 'expected one $eventName');
    return match.single.properties;
  }

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(_RecordedEvent(eventName, properties ?? const {}));
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void registerSuperProperties(Map<String, Object> properties) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}

class _RecordedEvent {
  const _RecordedEvent(this.eventName, this.properties);

  final String eventName;
  final Map<String, Object> properties;
}
