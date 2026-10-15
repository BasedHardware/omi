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
  final payloadReads = <Completer<Object?>>[];

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
  Future<Object?> getFeatureFlagPayload(String key) {
    final completer = Completer<Object?>();
    payloadReads.add(completer);
    return completer.future;
  }

  final variantReads = <Completer<String?>>[];
  final reloads = <Completer<bool>>[];

  @override
  Future<bool> reloadFeatureFlags() {
    final completer = Completer<bool>();
    reloads.add(completer);
    return completer.future;
  }

  @override
  Future<String?> getFeatureFlagVariant(String key) {
    final completer = Completer<String?>();
    variantReads.add(completer);
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

  test('payload read respects settled identity and consent', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');
    final read = AnalyticsManager().getFeatureFlagPayload('mobile_store_review_tuning');
    adapter.payloadReads.single.complete({'reading_seconds': 5});
    expect(await read, {'reading_seconds': 5});
    final second = AnalyticsManager().getFeatureFlagPayload('mobile_store_review_tuning');
    AnalyticsManager().optOutTracking();
    adapter.payloadReads.last.complete({'reading_seconds': 1});
    expect(await second, isNull);
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

  test('an experiment exposure is sent once per identity and arm, and again for a new identity', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    expect(AnalyticsManager().recordFeatureFlagExposure('paywall-variant', 'control'), isFalse,
        reason: 'nothing to attribute to before an identity settles');

    await settleIdentity(adapter, 'user-a');
    expect(AnalyticsManager().recordFeatureFlagExposure('paywall-variant', 'control'), isTrue);
    expect(AnalyticsManager().recordFeatureFlagExposure('paywall-variant', 'control'), isFalse);
    expect(AnalyticsManager().recordFeatureFlagExposure('paywall-variant', 'outline'), isTrue);

    await settleIdentity(adapter, 'user-b');
    expect(AnalyticsManager().recordFeatureFlagExposure('paywall-variant', 'control'), isTrue,
        reason: 'a different account is exposed in its own right');
  });

  test('a failed flag reload is reported as false even when a stale flag reads enabled', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');

    final reload = AnalyticsManager().reloadFeatureFlags();
    adapter.reloads.single.complete(false);
    expect(await reload, isFalse);

    final read = AnalyticsManager().isFeatureEnabled('onboarding-webview');
    adapter.flagReads.single.complete(true);
    expect(await read, isTrue, reason: 'the stale value is still readable; callers must not read after a false reload');
  });

  test('a reload that errors or outlives an identity switch is false', () async {
    final adapter = _FlagAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    await settleIdentity(adapter, 'user-a');

    final errored = AnalyticsManager().reloadFeatureFlags();
    adapter.reloads.last.completeError(StateError('offline'));
    expect(await errored, isFalse);

    final slow = AnalyticsManager().reloadFeatureFlags();
    await settleIdentity(adapter, 'user-b');
    adapter.reloads.last.complete(true);
    expect(await slow, isFalse, reason: "A's answer arrived after B settled");
  });
}
