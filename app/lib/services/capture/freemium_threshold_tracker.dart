import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/utils/logger.dart';

class FreemiumThresholdTracker {
  bool _reached = false;
  int _remainingSeconds = 0;
  bool _requiresUserAction = false;

  bool get reached => _reached;
  int get remainingSeconds => _remainingSeconds;
  bool get requiresUserAction => _requiresUserAction;

  /// S18: the listen threshold event is the Plus meter warning only.
  /// Basic enters on-device through S17; this sheet stays opt-in from Settings.
  static bool shouldShowPlusMeterPaywall({
    required bool reached,
    required bool requiresUserAction,
    required PlanType? plan,
  }) {
    return reached && requiresUserAction && plan == PlanType.plus;
  }

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
