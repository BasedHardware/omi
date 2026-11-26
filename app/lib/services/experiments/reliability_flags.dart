import 'package:omi/utils/analytics/analytics_manager.dart';

/// Remote switches of the recording-reliability rollouts, one flag-store key per behaviour.
///
/// Lifecycle: rollout; default off. The app reads them from the account's Omi flag snapshot
/// (`GET /v1/flags`), so each is off until the snapshot has loaded and off for an account the
/// rule does not admit. The backend evaluates the same key for the same account
/// (backend/config/reliability_experiments.py), so one rule switches both sides.
///
/// Names (the keys of [keys]) are what `ReliabilityExperiments.enabled` takes; a name without a
/// key here has no remote switch and can only be selected in a local development build.
abstract final class ReliabilityFlags {
  static const Map<String, String> keys = {
    'end_open_conversation': _EndOpenConversation.enabledFlag,
    'fast_end_feedback': _FastEndFeedback.enabledFlag,
    'end_button_by_device': _EndButtonByDevice.enabledFlag,
    'instant_live_text': _InstantLiveText.enabledFlag,
    'early_title_icon': _EarlyTitleIcon.enabledFlag,
    'receipt_long_poll': _ReceiptLongPoll.enabledFlag,
    'vendor_recognizer_on_opened_app': _VendorRecognizerOnOpenedApp.enabledFlag,
  };

  /// The cached answer for [name]; never throws and never waits. False before the account's
  /// flags have loaded, for an unknown name, and when analytics has no settled identity.
  static bool enabled(String name, {bool Function(String key)? readFlag}) {
    final key = keys[name];
    if (key == null) return false;
    try {
      return (readFlag ?? AnalyticsManager().isBooleanFeatureEnabledCached)(key);
    } catch (_) {
      return false;
    }
  }
}

// One class per key: the flag registry check reads `enabledFlag` literals in this folder.
abstract final class _EndOpenConversation {
  static const enabledFlag = 'end_open_conversation';
}

abstract final class _FastEndFeedback {
  static const enabledFlag = 'fast_end_feedback';
}

abstract final class _EndButtonByDevice {
  static const enabledFlag = 'end_button_by_device';
}

abstract final class _InstantLiveText {
  static const enabledFlag = 'instant_live_text';
}

abstract final class _EarlyTitleIcon {
  static const enabledFlag = 'early_title_icon';
}

abstract final class _ReceiptLongPoll {
  static const enabledFlag = 'receipt_long_poll';
}

abstract final class _VendorRecognizerOnOpenedApp {
  static const enabledFlag = 'vendor_recognizer_on_opened_app';
}
