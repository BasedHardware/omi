import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';

class RefactorFlagAdapter
    implements AnalyticsAdapter, AnalyticsIdentityAdapter, AnalyticsFeatureFlagAdapter, AnalyticsBooleanFlagAdapter {
  RefactorFlagAdapter(this.flags);
  final Map<String, bool> flags;
  bool initialized = false;
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
    return flags[key] == true;
  }

  @override
  Future<bool> isBooleanFeatureEnabled(String key) async => flags[key] == true;
  @override
  Future<bool> isFeatureEnabled(String key) async => flags[key] == true;
  @override
  Future<bool> reloadFeatureFlags() async => true;
  @override
  Future<Object?> getFeatureFlagPayload(String key) async => null;
  @override
  Future<String?> getFeatureFlagVariant(String key) async => null;
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<RefactorFlagAdapter> setRefactorFlags(Map<String, bool> flags) async {
  AnalyticsManager.resetForTesting();
  PackageInfo.setMockInitialValues(
      appName: 'Test', packageName: 'test', version: '1', buildNumber: '1', buildSignature: '');
  final adapter = RefactorFlagAdapter(flags);
  AnalyticsManager.configure(adapter);
  await AnalyticsManager.init();
  AnalyticsManager().bindIdentity('synthetic-owner');
  await Future<void>.delayed(Duration.zero);
  return adapter;
}
