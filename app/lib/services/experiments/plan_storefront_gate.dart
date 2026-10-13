import 'package:omi/utils/analytics/analytics_manager.dart';

/// Client presentation gates only. Backend visibility and entitlement decisions win.
/// Lifecycle: rollout; owner: dazheng; review-by: 2026-11-12; default off.
abstract final class PlanStorefrontGate {
  static const sheetFlag = 'mobile-plan-storefront';
  static const upsellFlag = 'mobile-contextual-upsells';

  static Future<bool> sheetEnabled({Future<bool> Function(String)? readFlag}) => _read(sheetFlag, readFlag);
  static Future<bool> upsellsEnabled({Future<bool> Function(String)? readFlag}) => _read(upsellFlag, readFlag);

  static Future<bool> _read(String key, Future<bool> Function(String)? readFlag) async {
    try {
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(key).timeout(const Duration(seconds: 2));
    } catch (_) {
      return false;
    }
  }
}
