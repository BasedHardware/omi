import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart' show AnalyticsManager;
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/analytics/registry/typed_events.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/spine/contract.dart';

class RecordingAdapter implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];
  final superProperties = <String, Object>{};
  bool initialized = false;
  @override
  bool get isInitialized => initialized;
  @override
  Future<void> init() async => initialized = true;
  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, Map.of(properties ?? {})));
  @override
  void registerSuperProperties(Map<String, Object> properties) => superProperties.addAll(properties);
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

List<List<Object>> emissionPayloads(List<(String, Map<String, Object>)> events) =>
    events.map((event) => <Object>[event.$1, event.$2]).toList();

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  contractTest('C7 complete example batch emits byte-identical names/properties through existing queue', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final legacy = AnalyticsManager();
    legacy.onboardingCompleted();
    legacy.phoneMicRecordingStarted();
    legacy.phoneMicRecordingStopped();
    legacy.transcribeLaterToggled(enabled: false);
    legacy.transcribeLaterToggled(enabled: true);
    await AnalyticsManager.flushPending(force: true);
    final expected = List.of(adapter.events);
    expect(expected.map((e) => e.$1), [
      'Onboarding Completed',
      'Phone Mic Recording Started',
      'Phone Mic Recording Stopped',
      'Transcribe Later Toggled',
      'Transcribe Later Toggled'
    ]);
    expect(expected[3].$2['enabled'], false);
    expect(expected[4].$2['enabled'], true);
    adapter.events.clear();
    const typed = TypedEvents();
    for (final event in <RegisteredEvent>[
      const OnboardingCompleted(),
      const PhoneMicRecordingStarted(),
      const PhoneMicRecordingStopped(),
      const TranscribeLaterToggled(enabled: false),
      const TranscribeLaterToggled(enabled: true)
    ]) {
      typed.emit(event);
    }
    await AnalyticsManager.flushPending(force: true);
    expect(emissionPayloads(adapter.events), emissionPayloads(expected));
    expect(adapter.superProperties.keys, containsAll(['git_sha', 'build_number']));
    expect(adapter.events.every((e) => !e.$2.containsKey('correlation_id')), isTrue);
  });

  contractTest('C7 typed event uses existing pre-init queue and flushes exactly once', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    const TypedEvents().emit(const TranscribeLaterToggled(enabled: false));
    expect(adapter.events, isEmpty);
    expect(AnalyticsManager.queuedEventCountForTesting, 1);
    await AnalyticsManager.init();
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    expect(adapter.events, hasLength(1));
    expect(adapter.events.single.$1, 'Transcribe Later Toggled');
    expect(adapter.events.single.$2['enabled'], false);
  });

  contractTest('C7 missing analytics configuration remains a no-op without a second sink', () async {
    const TypedEvents().emit(const PhoneMicRecordingStarted());
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
    expect(AnalyticsManager.droppedEventCountForTesting, 0);
  });
}
