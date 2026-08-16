import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('init returns when the analytics SDK hangs', () async {
    final adapter = _FakeAnalyticsAdapter(hangInit: true);
    AnalyticsManager.configure(adapter);

    final elapsed = Stopwatch()..start();
    await AnalyticsManager.init(timeout: const Duration(milliseconds: 10));
    elapsed.stop();

    expect(adapter.isInitialized, isFalse);
    expect(elapsed.elapsed, lessThan(const Duration(milliseconds: 250)));
  });

  test('track queues events and flushes them after init', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);

    AnalyticsManager().track('Queued Event', properties: {'count': 1, 'ignored': null});
    expect(adapter.events, isEmpty);
    expect(AnalyticsManager.queuedEventCountForTesting, 1);

    await AnalyticsManager.init();
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, hasLength(1));
    expect(adapter.events.single.eventName, 'Queued Event');
    expect(adapter.events.single.properties, {'count': 1});
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });

  test('page opens register context for native interaction events', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().pageOpened('Settings');

    expect(adapter.interactionContexts, [const _InteractionContext(screenName: 'Settings', target: 'screen')]);
  });

  test('track retries adapter failures without throwing through the caller', () async {
    final adapter = _FakeAnalyticsAdapter(trackFailuresBeforeSuccess: 1);
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();

    AnalyticsManager().track('Retry Event');
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, isEmpty);
    expect(AnalyticsManager.queuedEventCountForTesting, 1);

    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, hasLength(1));
    expect(adapter.events.single.eventName, 'Retry Event');
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });

  test('retry delay sequence starts with the first backoff slot', () {
    expect(AnalyticsManager.retryDelayForTesting(0), const Duration(seconds: 1));
    expect(AnalyticsManager.retryDelayForTesting(1), const Duration(seconds: 5));
    expect(AnalyticsManager.retryDelayForTesting(2), const Duration(seconds: 30));
    expect(AnalyticsManager.retryDelayForTesting(3), const Duration(seconds: 30));
    expect(AnalyticsManager.retryDelayForTesting(4), const Duration(seconds: 30));
  });

  test('queue is bounded and drops oldest events under pressure', () {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);

    for (var i = 0; i < 205; i++) {
      AnalyticsManager().track('Queued Event $i');
    }

    expect(AnalyticsManager.queuedEventCountForTesting, 200);
    expect(AnalyticsManager.droppedEventCountForTesting, 5);
  });
}

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  _FakeAnalyticsAdapter({this.hangInit = false, this.trackFailuresBeforeSuccess = 0});

  final bool hangInit;
  int trackFailuresBeforeSuccess;
  final List<_RecordedEvent> events = [];
  final List<_InteractionContext> interactionContexts = [];
  bool _initialized = false;

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    if (hangInit) {
      await Completer<void>().future;
    }
    _initialized = true;
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    if (trackFailuresBeforeSuccess > 0) {
      trackFailuresBeforeSuccess--;
      throw StateError('analytics unavailable');
    }
    events.add(_RecordedEvent(eventName, properties ?? const {}));
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {
    interactionContexts.add(_InteractionContext(screenName: screenName, target: target));
  }

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

class _InteractionContext {
  const _InteractionContext({required this.screenName, required this.target});

  final String? screenName;
  final String target;

  @override
  bool operator ==(Object other) =>
      other is _InteractionContext && other.screenName == screenName && other.target == target;

  @override
  int get hashCode => Object.hash(screenName, target);
}
