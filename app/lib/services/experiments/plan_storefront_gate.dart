import 'package:omi/utils/analytics/analytics_manager.dart';

/// Client presentation gates only. Backend visibility and entitlement decisions win.
/// Lifecycle: rollout; owner: dazheng; review-by: 2026-11-12; default off.
abstract final class PlanStorefrontGate {
  static const enabledFlag = 'mobile-plan-storefront';
  static const sheetFlag = enabledFlag;
  static const upsellFlag = _ContextualUpsellsGate.enabledFlag;

  /// Kill switch for the yearly-first plan picker. False/missing/offline/error
  /// keeps yearly preselected (ops_kill, owner dazheng); true returns the sheet
  /// to monthly-first on the next open without a release.
  static const killSwitchFlag = 'mobile-plan-storefront-yearly-default-off';

  static Future<bool> sheetEnabled({Future<bool> Function(String)? readFlag}) => _read(sheetFlag, readFlag);
  static Future<bool> upsellsEnabled({Future<bool> Function(String)? readFlag}) => _read(upsellFlag, readFlag);

  static Future<bool> yearlyDefaultEnabled({Future<bool> Function(String)? readFlag}) async {
    try {
      final killed =
          await (readFlag ?? AnalyticsManager().isFeatureEnabled)(killSwitchFlag).timeout(const Duration(seconds: 1));
      return !killed;
    } catch (_) {
      return true;
    }
  }

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
