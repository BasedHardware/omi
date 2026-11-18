import 'package:flutter/foundation.dart';

import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';

/// Quick Summary: Finish opens the conversation, streams a short summary while the full one is
/// written, and polls processing rows faster. Lifecycle: rollout; owner: mobile; default off.
/// Fail-closed: no settled identity or no cached flag means off.
///
/// Recordings-and-conversations (v3) accounts never get it: their capture ends as a recording whose
/// conversation is derived later and summarised by its own live section, so Finish keeps v3's Home.
/// Until the server has answered "not v3" for this account, the gate stays off.
abstract final class QuickSummaryGate {
  /// Omi flag store boolean.
  static const enabledFlag = 'mobile-quick-summary';

  /// Debug and profile builds only: `--dart-define=OMI_INTERIM_SUMMARY=true` forces it on.
  static const _debugForce = bool.fromEnvironment('OMI_INTERIM_SUMMARY');

  /// Tests force the gate with this (reset it in a tearDown); null reads the flag.
  @visibleForTesting
  static bool? debugOverride;

  static bool get isEnabled =>
      debugOverride ??
      (((!kReleaseMode && _debugForce) || AnalyticsManager().isBooleanFeatureEnabledCached(enabledFlag)) &&
          ConversationsV3Provider.rememberedLegacy());
}
