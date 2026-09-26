import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

class _FlagAdapter implements AnalyticsAdapter, AnalyticsIdentityAdapter, AnalyticsFeatureFlagAdapter {
  bool _initialized = false;
  final settles = <Completer<String>>[];
  final flagReads = <Completer<bool>>[];

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  Future<String> settleIdentity(String? identity, {required bool reset}) {
    final completer = Completer<String>();
    settles.add(completer);
    return completer.future;
  }

  @override
  Future<bool> isFeatureEnabled(String key) {
    final completer = Completer<bool>();
    flagReads.add(completer);
    return completer.future;
  }

  @override
  void track({required String eventName, Map<String, Object>? properties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

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

class _PlainAdapter implements AnalyticsAdapter {
  bool _initialized = false;

  @override
  bool get isInitialized => _initialized;

  @override
  Future<void> init() async {
    _initialized = true;
  }

  @override
  void track({required String eventName, Map<String, Object>? properties}) {}

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

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

  Future<void> settleIdentity(_FlagAdapter adapter, String identity) async {
    AnalyticsManager().bindIdentity(identity);
    adapter.settles.last.complete(identity);
    await pumpEventQueue();
  }

  test('returns the adapter answer once identity has settled', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');

    final read = AnalyticsManager().isFeatureEnabled('mobile-capture-recovery-v1');
    adapter.flagReads.single.complete(true);
    expect(await read, isTrue);
  });

  test('an identity switch while the flag read is in flight fails closed', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');

    final read = AnalyticsManager().isFeatureEnabled('mobile-capture-recovery-v1');
    AnalyticsManager().bindIdentity('user-b');
    adapter.flagReads.single.complete(true);

    expect(await read, isFalse);
  });

  test('a consent withdrawal while the flag read is in flight fails closed', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');

    final read = AnalyticsManager().isFeatureEnabled('mobile-capture-recovery-v1');
    AnalyticsManager().optOutTracking();
    adapter.flagReads.single.complete(true);

    expect(await read, isFalse);
  });

  test('unsettled identity returns false without asking the adapter', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    AnalyticsManager().bindIdentity('user-a');

    expect(await AnalyticsManager().isFeatureEnabled('mobile-capture-recovery-v1'), isFalse);
    expect(adapter.flagReads, isEmpty);
  });

  test('an adapter without feature-flag support returns false', () async {
    final adapter = _PlainAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    AnalyticsManager().bindIdentity('user-a');
    await pumpEventQueue();

    expect(await AnalyticsManager().isFeatureEnabled('mobile-capture-recovery-v1'), isFalse);
  });

  test('a throwing flag read returns false', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');

    final read = AnalyticsManager().isFeatureEnabled('mobile-capture-recovery-v1');
    adapter.flagReads.single.completeError(StateError('sdk unavailable'));

    expect(await read, isFalse);
  });
}
