import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';

class RefactorFlagAdapter
    implements
        AnalyticsAdapter,
        AnalyticsIdentityAdapter,
        AnalyticsFeatureFlagAdapter,
        AnalyticsBooleanFlagAdapter,
        AnalyticsResolvedFlagAdapter {
  RefactorFlagAdapter(this.flags) : cachedFlags = Map<String, bool>.from(flags);
  final Map<String, bool> flags;
  final Map<String, bool> cachedFlags;
  final Set<String> multivariateFlags = {};
  bool initialized = false;
  int reloadFailuresRemaining = 0;
  void Function()? onCachedRead;
  @override
  bool get isInitialized => initialized;
  @override
  Future<void> init() async {
    initialized = true;
  }

  @override
  Future<String> settleIdentity(String? identity, {required bool reset}) async => identity ?? 'synthetic-owner';
  @override
  bool isBooleanFeatureEnabledCached(String key) {
    onCachedRead?.call();
    return cachedFlags[key] == true && !multivariateFlags.contains(key);
  }

  @override
  Future<bool> isBooleanFeatureEnabled(String key) async =>
      cachedFlags[key] == true && !multivariateFlags.contains(key);
  @override
  Future<bool?> resolvedFeatureEnabled(String key) async => cachedFlags[key];
  @override
  Future<bool> isFeatureEnabled(String key) async => flags[key] == true;
  @override
  Future<bool> reloadFeatureFlags() async {
    if (reloadFailuresRemaining > 0) {
      reloadFailuresRemaining--;
      return false;
    }
    cachedFlags
      ..clear()
      ..addAll(flags);
    return true;
  }

  @override
  Future<Object?> getFeatureFlagPayload(String key) async => null;
  @override
  Future<String?> getFeatureFlagVariant(String key) async => null;
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<RefactorFlagAdapter> setRefactorFlags(Map<String, bool> flags, {int reloadFailures = 0}) async {
  AnalyticsManager.resetForTesting();
  PackageInfo.setMockInitialValues(
      appName: 'Test', packageName: 'test', version: '1', buildNumber: '1', buildSignature: '');
  final adapter = RefactorFlagAdapter(flags)..reloadFailuresRemaining = reloadFailures;
  AnalyticsManager.configure(adapter);
  await AnalyticsManager.init();
  AnalyticsManager().bindIdentity('synthetic-owner');
  await Future<void>.delayed(Duration.zero);
  return adapter;
}
