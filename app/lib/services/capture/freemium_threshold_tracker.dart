import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/utils/logger.dart';

class FreemiumThresholdTracker {
  bool _reached = false;
  int _remainingSeconds = 0;
  bool _requiresUserAction = false;

  bool get reached => _reached;
  int get remainingSeconds => _remainingSeconds;
  bool get requiresUserAction => _requiresUserAction;

  bool handle(FreemiumThresholdReachedEvent event) {
    if (_reached) return false;

    _reached = true;
    _remainingSeconds = event.remainingSeconds;
    _requiresUserAction = event.requiresUserAction;

    Logger.debug('[Freemium] Threshold reached - ${event.remainingSeconds} seconds remaining');
    Logger.debug('[Freemium] Action required: ${event.action.name}, requires user action: ${event.requiresUserAction}');

    if (event.requiresUserAction) {
      Logger.debug('[Freemium] User should setup on-device transcription in Settings > Transcription');
    } else {
      Logger.debug('[Freemium] No user action required - backend will handle fallback');
    }

    return true;
  }

  void reset() {
    _reached = false;
    _remainingSeconds = 0;
    _requiresUserAction = false;
  }
}
