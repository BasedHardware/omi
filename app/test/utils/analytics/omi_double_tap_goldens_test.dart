import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Adapter payloads captured from [AnalyticsManager.omiDoubleTap] at
/// `83f542891a4d514c2bbf94d419767af51b16b6f2`, before the unused
/// `additionalProperties` Map parameter was removed. Production callers pass
/// only `feature`; these five values are every live call site.
const omiDoubleTapPreRemovalSha = '83f542891a4d514c2bbf94d419767af51b16b6f2';

const omiDoubleTapFeatures = <String>[
  'unmute',
  'mute',
  'star_conversation',
  'unstar_conversation',
  'process_conversation',
];

void fireOmiDoubleTapFeatures(AnalyticsManager analytics) {
  for (final feature in omiDoubleTapFeatures) {
    analytics.omiDoubleTap(feature: feature);
  }
}

List<List<Object>> omiDoubleTapGoldens(Map<String, Object> globals) => [
      for (final feature in omiDoubleTapFeatures)
        [
          'Omi Double Tap',
          {...globals, 'feature': feature},
        ],
    ];

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

  test('Omi Double Tap payloads match goldens pinned at $omiDoubleTapPreRemovalSha', () async {
    final adapter = _FakeAnalyticsAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireOmiDoubleTapFeatures(AnalyticsManager());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '2.3.4',
      'app_build': '567',
    };
    expect(_emissionPayloads(adapter.events), omiDoubleTapGoldens(globals));
    expect(adapter.events, hasLength(omiDoubleTapFeatures.length));
    expect(
      adapter.events.every((event) => event.properties.keys.toSet().difference({'feature', ...globals.keys}).isEmpty),
      isTrue,
    );
    expect(adapter.events.every((event) => !event.properties.containsKey('correlation_id')), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });
}

List<List<Object>> _emissionPayloads(List<_RecordedEvent> events) => [
      for (final event in events) [event.eventName, event.properties],
    ];

class _FakeAnalyticsAdapter implements AnalyticsAdapter {
  final List<_RecordedEvent> events = [];
  bool _initialized = false;

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
    events.add(_RecordedEvent(eventName, Map<String, Object>.from(properties ?? const {})));
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
