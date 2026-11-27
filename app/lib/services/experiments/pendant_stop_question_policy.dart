import 'package:omi/utils/analytics/analytics_manager.dart';

/// The survey is enabled unless the Omi flag store explicitly turns it off.
class PendantStopQuestionPolicy {
  static const killSwitchFlag = 'pendant_stop_question_off';
  static Future<bool> disabled() => AnalyticsManager().isFeatureEnabled(killSwitchFlag);
}
