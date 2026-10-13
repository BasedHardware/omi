import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/pages/onboarding/guided_voice_controller.dart';
import '../../providers/guided_voice_experience_test.dart' show ExperienceIO, typedReview;

void main() {
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  test('controller failure taxonomy emits unchanged event names and transcription path', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    for (final kind in ['permission_denied', 'permission_permanently_denied', 'engine_start_failed']) {
      final io = ExperienceIO()..failure = GuidedVoiceFailure(kind);
      final flow = GuidedVoiceController(io);
      await flow.start();
      flow.dispose();
    }
    for (final kind in ['transcribe_timeout', 'transcribe_http_error', 'transcribe_empty']) {
      final io = ExperienceIO();
      final flow = GuidedVoiceController(io);
      await flow.start();
      io.speak();
      io.failure = GuidedVoiceFailure(kind);
      await flow.next();
      flow.dispose();
    }
    await AnalyticsManager.flushPending(force: true);
    final recording = adapter.events.where((e) => e.eventName == 'Guided Intro Recording Failed').toList();
    final transcription = adapter.events.where((e) => e.eventName == 'Guided Intro Prompt Completed').toList();
    expect(recording.map((e) => e.properties['failure_class']),
        ['permission_denied', 'permission_permanently_denied', 'engine_start_failed']);
    expect(transcription.map((e) => e.properties['failure_class']),
        ['transcribe_timeout', 'transcribe_http_error', 'transcribe_empty']);
    for (final event in [...recording, ...transcription]) {
      expect(event.properties['transcription_path'], 'cloud');
      expect(event.properties.keys, isNot(contains('transcript')));
    }
  });

  test('on-device failures carry the on_device path', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final io = ExperienceIO()..local = true;
    final flow = GuidedVoiceController(io);
    await flow.start();
    io.speak();
    io.failure = const GuidedVoiceFailure('transcribe_timeout');
    await flow.next();
    flow.dispose();
    await AnalyticsManager.flushPending(force: true);
    final event = adapter.events.singleWhere((e) => e.eventName == 'Guided Intro Prompt Completed');
    expect(event.properties['transcription_path'], 'on_device');
    expect(event.properties['failure_class'], 'transcribe_timeout');
  });

  test('payoff controller emits shown and continued once, with no answer content', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    for (final fail in [false, true]) {
      final flow = GuidedVoiceController(ExperienceIO()..chatFails = fail);
      await typedReview(flow);
      await flow.saveAll();
      await flow.showPayoff('Question', 'Saved answer summary');
      await flow.showPayoff('Question', 'Another summary');
      flow.continuePayoff();
      flow.continuePayoff();
      flow.dispose();
    }
    await AnalyticsManager.flushPending(force: true);
    final shown = adapter.events.where((e) => e.eventName == 'Guided Intro Payoff Shown').toList();
    expect(shown, hasLength(2));
    expect(shown.map((e) => e.properties['answer_source']), ['chat', 'fallback']);
    for (final event in shown) {
      expect(event.properties['memories_count'], 1);
      expect(event.properties['latency_ms'], isA<int>());
      expect(event.properties.keys, isNot(contains('answer')));
    }
    expect(adapter.events.where((e) => e.eventName == 'Guided Intro Payoff Continued'), hasLength(2));
  });

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
