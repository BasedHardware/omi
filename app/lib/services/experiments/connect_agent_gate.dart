import 'package:flutter/foundation.dart';

import 'package:omi/utils/analytics/analytics_manager.dart';

/// Client gate for the in-app Connect an Agent screens (ChatGPT one tap, computer agents with a
/// one-time key, and "Ask About This Conversation"). Off keeps today's behavior: the Settings row
/// opens the web developer home and conversations have no ask entry. Fail-closed: no analytics
/// identity, a slow read or an error all mean off.
abstract final class ConnectAgentGate {
  /// PostHog flag key (project 302298). Registered in `config/feature-flags.yaml`.
  static const enabledFlag = 'mobile-connect-agent-hub';

  /// Debug builds only: `--dart-define=OMI_CONNECT_AGENT_HUB=true` turns the screens on.
  /// `kDebugMode` excludes every store build.
  static const _debugOverride = bool.fromEnvironment('OMI_CONNECT_AGENT_HUB');

  static Future<bool> isEnabled({Future<bool> Function(String key)? readFlag}) async {
    if (kDebugMode && _debugOverride) return true;
    try {
      // `then<bool>` first: a reader typed `Future<Never>` would otherwise make `timeout` reject
      // `onTimeout` before it listens, leaving the reader's error unhandled.
      return await (readFlag ?? AnalyticsManager().isFeatureEnabled)(enabledFlag)
          .then<bool>((enabled) => enabled)
          .timeout(const Duration(seconds: 2), onTimeout: () => false);
    } catch (_) {
      return false;
    }
  }
}
