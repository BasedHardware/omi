import 'package:omi/utils/analytics/analytics_manager.dart';

/// Kill switch for the end-of-recording marker. On unless the flag resolves
/// true: the marker deletes nothing and changes no custody, so an unknown or
/// unreadable flag keeps it on.
class CaptureEndMarkerPolicy {
  static const killSwitchFlag = 'upload_end_marker_off';
  static Future<bool> disabled() => AnalyticsManager().isFeatureEnabled(killSwitchFlag);
}
