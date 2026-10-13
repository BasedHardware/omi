import 'package:omi/utils/analytics/analytics_manager.dart';

/// Client presentation gates only. Backend visibility and entitlement decisions win.
/// Lifecycle: rollout; owner: dazheng; review-by: 2026-11-12; default off.
abstract final class PlanStorefrontGate {
  static const enabledFlag = 'mobile-plan-storefront';
  static const sheetFlag = enabledFlag;
  static const upsellFlag = _ContextualUpsellsGate.enabledFlag;

  static Future<bool> sheetEnabled({Future<bool> Function(String)? readFlag}) => _read(sheetFlag, readFlag);
  static Future<bool> upsellsEnabled({Future<bool> Function(String)? readFlag}) => _read(upsellFlag, readFlag);

  static Future<bool> contextualEnabled({Future<bool> Function(String)? readFlag}) async {
    final flags = await Future.wait([upsellsEnabled(readFlag: readFlag), sheetEnabled(readFlag: readFlag)]);
    return flags.every((enabled) => enabled);
  }

  static Future<bool> _read(String key, Future<bool> Function(String)? readFlag) async {
    try {
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(key).timeout(const Duration(seconds: 2));
    } catch (_) {
      return false;
    }
  }
}

/// Independent rollout key, using the shared mobile registry's enabledFlag convention.
abstract final class _ContextualUpsellsGate {
  static const enabledFlag = 'mobile-contextual-upsells';
}
