part of 'analytics_manager.dart';

extension AnalyticsFlagReader on AnalyticsManager {
  /// Synchronous reads use the same settled-identity fence as async flag reads.
  bool refactorClientsEnabled(String key) {
    final adapter = AnalyticsManager._adapter;
    if (adapter == null ||
        !adapter.isInitialized ||
        !AnalyticsManager._trackingEnabled ||
        AnalyticsManager._settledDistinctId == null ||
        adapter is! AnalyticsBooleanFlagAdapter) {
      return false;
    }
    final epoch = AnalyticsManager._identityEpoch;
    final identity = AnalyticsManager._settledDistinctId;
    try {
      final enabled = (adapter as AnalyticsBooleanFlagAdapter).isBooleanFeatureEnabledCached(key);
      return enabled &&
          epoch == AnalyticsManager._identityEpoch &&
          identical(identity, AnalyticsManager._settledDistinctId) &&
          AnalyticsManager._trackingEnabled;
    } catch (_) {
      return false;
    }
  }

  /// One fenced read per flag value: no adapter/identity, tracking off or an identity switch mid-read → null.
  Future<T?> _readFlag<T>(Future<T> Function(AnalyticsFeatureFlagAdapter adapter) read,
      {Duration timeout = AnalyticsManager._initTimeout}) async {
    final adapter = AnalyticsManager._adapter;
    if (adapter == null ||
        !adapter.isInitialized ||
        !AnalyticsManager._trackingEnabled ||
        AnalyticsManager._settledDistinctId == null) {
      return null;
    }
    if (adapter is! AnalyticsFeatureFlagAdapter) return null;
    final epoch = AnalyticsManager._identityEpoch;
    final identity = AnalyticsManager._settledDistinctId;
    try {
      final value = await read(adapter as AnalyticsFeatureFlagAdapter).timeout(timeout);
      if (epoch != AnalyticsManager._identityEpoch ||
          !identical(identity, AnalyticsManager._settledDistinctId) ||
          !AnalyticsManager._trackingEnabled) {
        return null;
      }
      return value;
    } catch (_) {
      return null;
    }
  }
}
