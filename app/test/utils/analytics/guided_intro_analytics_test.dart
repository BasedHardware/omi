import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

void main() {
  setUp(AnalyticsManager.resetForTesting);
  tearDown(AnalyticsManager.resetForTesting);

  test('guided intro events carry bounded funnel properties without content', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    final analytics = AnalyticsManager();
    analytics.guidedIntroStarted(
      sessionId: 'session-1',
      source: 'first_run',
      variant: 'guided_voice_v1',
      promptCount: 4,
    );
    analytics.guidedIntroPromptCompleted(
      sessionId: 'session-1',
      source: 'first_run',
      variant: 'guided_voice_v1',
      promptIndex: 3,
      result: 'answered',
      durationMs: 1200,
      transcriptPresent: true,
    );
    analytics.guidedIntroCompleted(
      sessionId: 'session-1',
      source: 'first_run',
      variant: 'guided_voice_v1',
      completionMode: 'saved',
      voiceResult: 'success',
      memorySaved: 3,
      goalResult: 'saved',
      elapsedMs: 45000,
    );
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.map((event) => event.eventName), [
      'Guided Intro Started',
      'Guided Intro Prompt Completed',
      'Guided Intro Completed',
    ]);
    expect(adapter.events[1].properties, containsPair('prompt_index', 3));
    expect(adapter.events[1].properties, containsPair('result', 'answered'));
    expect(adapter.events[1].properties.keys, isNot(contains('transcript')));
    expect(adapter.events[2].properties, containsPair('completion_mode', 'saved'));
  });
}

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  final events = <_RecordedEvent>[];
  bool initialized = false;

  @override
  bool get isInitialized => initialized;

  @override
  Future<void> init() async => initialized = true;

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
