import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// One page for a conversation in progress on a conversations v3 account.
///
/// Off, the live page (`LiveEpisodePage`) and the conversation page are two layouts for the same
/// conversation, and which one opens depends on the row tapped. On, the live page draws the
/// conversation page's layout (title, Summary and Transcript, Pause and End) while the server has not
/// made the conversation yet, and becomes that conversation's page in place once the server lists it.
///
/// Evaluated from the Omi flag [enabledFlag], registered in `config/feature-flags.yaml`. Fail-closed:
/// no analytics identity, a failed read or a missing rule is off. Read when the analytics identity
/// settles and again when it changes; a page already open keeps the layout it opened with until its
/// next build. Lifecycle: rollout; default off.
abstract final class LiveConversationPageGate {
  static const enabledFlag = 'mobile-live-conversation-page';

  /// Debug-build override: `--dart-define=OMI_LIVE_CONVERSATION_PAGE=true`.
  static const _debugForce = bool.fromEnvironment('OMI_LIVE_CONVERSATION_PAGE');

  /// A `local_dev` profile build runs against a local stack and has no flag snapshot, so no flag
  /// read can answer true there. The same define therefore also applies to that profile.
  static const _localDevProfile = String.fromEnvironment('OMI_APP_PROFILE') == 'local_dev';

  static bool get debugOverrideActive => (kDebugMode || _localDevProfile) && _debugForce;

  static final ValueNotifier<bool> _flag = ValueNotifier(false);
  static bool _started = false;
  static int _read = 0;

  /// Tests set this to exercise either layout.
  @visibleForTesting
  static bool? debugOverride;

  /// Changes when a flag read changes the answer.
  static ValueListenable<bool> get changes => _flag;

  static bool get enabled => debugOverride ?? (debugOverrideActive || _flag.value);

  /// Called once at startup: follows the account's flag from then on.
  static void start() {
    if (_started) return;
    _started = true;
    AnalyticsManager.settledIdentity.addListener(_readFlag);
    _readFlag();
  }

  static Future<void> _readFlag() async {
    final read = ++_read;
    var flag = false;
    if (AnalyticsManager.settledIdentity.value != null) {
      try {
        flag = await AnalyticsManager().refreshBooleanFeatureFlag(enabledFlag);
      } catch (_) {
        flag = false;
      }
    }
    if (read != _read) return;
    _flag.value = flag;
  }
}
