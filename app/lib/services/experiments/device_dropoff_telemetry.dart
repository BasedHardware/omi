import 'package:omi/utils/analytics/analytics_manager.dart';

/// Kill switch for the drop-off fields on `Mobile Device Health Daily`. On
/// unless the flag resolves true: the fields only describe data the daily
/// event already reads, so an unknown or unreadable flag keeps them on.
class DeviceDropoffTelemetryPolicy {
  static const killSwitchFlag = 'device_dropoff_telemetry_off';
  static Future<bool> disabled() => AnalyticsManager().isFeatureEnabled(killSwitchFlag);
}
