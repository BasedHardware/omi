import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/app_session_telemetry.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late _FakeAnalyticsAdapter adapter;
  late AppSessionTelemetry telemetry;
  var nextId = 0;

  setUp(() async {
    nextId = 0;
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    telemetry = AppSessionTelemetry(
      createSessionId: () => 'session-${++nextId}',
    );
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('records one cold-start session', () async {
    telemetry.recordColdStart();
    telemetry.recordColdStart();
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events, hasLength(1));
    expect(adapter.events.single.eventName, 'App Session Started');
    expect(adapter.events.single.properties, containsPair('app_session_id', 'session-1'));
    expect(adapter.events.single.properties, containsPair('start_kind', 'coldStart'));
  });

  test('records a fresh session only after backgrounding', () async {
    telemetry.recordColdStart();
    telemetry.recordResumed();
    telemetry.recordBackgrounded();
    telemetry.recordResumed();
    telemetry.recordResumed();
    await AnalyticsManager.flushPending(force: true);

    expect(adapter.events.map((event) => event.eventName), ['App Session Started', 'App Session Started']);
    expect(adapter.events[0].properties, containsPair('app_session_id', 'session-1'));
    expect(adapter.events[0].properties, containsPair('start_kind', 'coldStart'));
    expect(adapter.events[1].properties, containsPair('app_session_id', 'session-2'));
    expect(adapter.events[1].properties, containsPair('start_kind', 'foreground'));
  });
}

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  final List<_RecordedEvent> events = [];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void identify({
    required String userId,
    Map<String, Object>? userProperties,
  }) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    events.add(_RecordedEvent(eventName, properties ?? const {}));
  }

  @override
  void setInteractionContext({String? screenName, required String target}) {}

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
