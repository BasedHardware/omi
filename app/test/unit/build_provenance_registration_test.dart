import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/build_provenance.dart';
import 'package:omi/utils/debugging/crashlytics_manager.dart';
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
      version: '1.0.543',
      buildNumber: '992',
      buildSignature: '',
    );
    await SharedPreferencesUtil.init();
  });

  tearDown(() {
    AnalyticsManager.resetForTesting();
  });

  test('init registers git_sha and build_number as super properties', () async {
    final adapter = _RecordingAdapter();
    AnalyticsManager.configure(adapter);

    await AnalyticsManager.init();

    expect(adapter.isInitialized, isTrue);
    expect(adapter.superProperties, containsPair('git_sha', 'unknown'));
    expect(adapter.superProperties, containsPair('build_number', 'unknown'));
    expect(adapter.superProperties.containsKey('shorebird_patch'), isFalse);
  });

  test('Crashlytics provenance keys match the analytics property names', () {
    final keys = BuildProvenance(
      gitSha: 'deadbeef',
      buildNumber: '1001',
      dirty: false,
    ).asProperties;
    expect(keys.keys.toList(), ['git_sha', 'build_number']);
    expect(keys['git_sha'], 'deadbeef');
    expect(keys['build_number'], '1001');
  });

  test('CrashlyticsManager.applyBuildProvenanceKeys is a no-op before Firebase', () async {
    // Trap: Crashlytics must not be touched before Firebase.initializeApp.
    // Host tests have no Firebase app; this must not throw.
    await CrashlyticsManager.applyBuildProvenanceKeys();
  });
}

class _RecordingAdapter implements AnalyticsAdapter {
  final Map<String, Object> superProperties = {};
  bool _initialized = false;

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  void registerSuperProperties(Map<String, Object> properties) {
    superProperties.addAll(properties);
  }

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
